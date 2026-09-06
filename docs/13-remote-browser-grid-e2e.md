# 13. Remote browser-grid e2e (ORES clusters, AWS + Hetzner)

**Issue:** [Doc 12](12-in-cluster-e2e.md) runs the browser suites with a browser
on the same machine as the test runner. But the ORES platform already operates
managed browser-automation servers on its AWS and Hetzner clusters — a shared,
maintained pool that's the right place to run UI e2e from CI without every
runner shipping Chromium. This doc is how the zed suites drive those remote
browser deployments, what's actually reachable, and the one architectural
constraint that shapes the whole thing.

## What the platform exposes (and what it doesn't)

`ORESoftware/k8s-cluster` deploys, in namespace `default` on both clouds
(`remote/argocd/dd-next-runtime/`):

- **`dd-browser-test-server`** (`:8104`) — a Fastify service that drives real
  Chromium through **all three back-ends** (Playwright, Puppeteer, Selenium)
  behind one declarative `POST /run` scenario API. This is the primary target.
- **`dd-selenium-server`** (`:8105`) — a standalone Selenium Grid + a Java
  scenario API.
- `dd-web-scraper` (`:8097`) and `dd-browser-job-runner` (`:8106`) — adjacent
  scraping / ephemeral-container-spawning services.

**There is no raw WebDriver/CDP endpoint exposed.** The Selenium Grid `:4444`
and any CDP `:9222` stay pod-internal — so you cannot point a stock Playwright
`connect()` / Selenium `RemoteWebDriver(url)` / Puppeteer `connect()` client at
a URL here. Automation goes through the `POST /run` DSL instead:
`goto`/`click`/`fill`/`waitForSelector`/`extractText`/`extractAttribute`/
`screenshot`/`press`/`select`/`waitForUrl` (see the service README). A run
returns `{ ok, finalUrl, finalTitle, extracted, screenshots, pageErrors }`.

(The zed harness still keeps env-gated `connect()` support —
`PW_CONNECT_WS` / `PUPPETEER_BROWSER_WS` / `SELENIUM_REMOTE_URL` in
[`playwright.config.ts`](https://github.com/zed-pkg/zed-e2e) and the
Puppeteer/Selenium specs — for the day a raw grid *is* exposed. It is inert
against the ORES `/run` servers.)

## Reaching it: gateway auth, and the in-cluster `/run` rule

- **Public, via the gateway.** Both clouds route the service under
  `/browser-test/*`, gated by the operator `Auth` header (local env
  `ALL_DOGS`); the gateway injects the inner `x-server-auth`. Reachable:
  `https://98.90.186.114/browser-test/...` (AWS node IP) and
  `https://hello.95-217-171-250.sslip.io/browser-test/...` (Hetzner). **But the
  gateway only exposes the GET diagnostics** (`/healthz`, `/tools`, `/status`,
  `/metrics`) — a `POST /browser-test/run` is `404` (the prefix isn't stripped
  and the service registers `/run` only at the bare path).
- **`POST /run` is in-cluster only.** Drive it from inside the cluster, e.g. by
  exec'ing the pod (it has Node 22 and its own `SERVER_AUTH_SECRET`):

  ```bash
  kubectl --context dd-ec2-runtime -n default exec deploy/dd-browser-test-server -- \
    node /dev/stdin <<'JS'
  const body = JSON.stringify({ tool: "playwright", steps: [
    { action: "goto", url: "https://example.com", waitUntil: "load" },
    { action: "waitForSelector", selector: "h1" },
    { action: "extractText", selector: "h1", name: "headline" } ] });
  fetch("http://localhost:8104/run", { method: "POST",
    headers: { "content-type": "application/json", "x-server-auth": process.env.SERVER_AUTH_SECRET },
    body }).then(r => r.json()).then(j => console.log(j.ok, j.extracted));
  JS
  ```

  Cluster access: **AWS** is a single kubeadm node reachable via the
  `dd-ec2-runtime` kube context (creds from `~/.aws`), or SSM Run Command on
  `i-0cc2461a55d491af6` when off-VPN. **Hetzner** is `ssh root@<ip>` with
  `~/.ssh/id_hetzner`, on-node `KUBECONFIG=/etc/kubernetes/admin.conf`.

## The constraint that shapes everything: the browser must reach the target

`/run` navigates *from inside the cluster*. So the URL under test must be
reachable **from that cluster** — a public URL, the cluster's own gateway, or an
in-cluster Service (ClusterDNS). A zed stack running in a local `kind` cluster
([doc 12](12-in-cluster-e2e.md)) is **not** reachable from AWS/Hetzner.
Therefore, to exercise the **zed UI** through the remote grid, the zed stack
must run in (or be reachable from) the same cluster as the browser server. The
in-memory profile deploys there as a ClusterIP service; the grid then points at
`http://dd-zed-web-server.<ns>.svc.cluster.local:8081`.

## Runner + scenarios

[`cluster/remote-grid.sh`](https://github.com/zed-pkg/zed-e2e/blob/main/cluster/remote-grid.sh)
codifies the in-cluster driver: given a kube context and a target web URL, it
POSTs the zed UI scenarios — declared inline in that script as `run_scenario
<tool> <name> <expected-substring> <steps-json>` calls — through the pod for
**each** of playwright / puppeteer / selenium and asserts the extracted text +
`finalTitle`. The scenarios mirror the local `web-ui`
checks: the home recency list renders, HTMX search returns a match, a package
page shows the `zed add …` snippet, and the security headers are present.

## Status: partially verified

- **AWS — both servers verified working.** `dd-browser-test-server` is healthy
  (`/tools` → Playwright 1.56, Puppeteer 24.43, Selenium 4.44) and an in-cluster
  `POST /run` ran a real navigate-and-extract through **all three** back-ends
  (example.com → `<h1>` "Example Domain": Playwright ~108ms, Puppeteer ~167ms,
  Selenium ~640ms). The dedicated **`dd-selenium-server`** (`:8105`, its own
  Grid on `:4444`) also ran a real scenario (`ok:true`, "Example Domain"), so
  the Selenium server is confirmed driving a browser, not just answering
  `/healthz`. AWS in-cluster access is the `dd-ec2-runtime` kube context; the
  node has `ctr`/`nerdctl` and the `dd-next-1` repo mounted (the self-build
  works).
- **Hetzner — down, root cause diagnosed (a platform bug, not the server).**
  The current cluster is the 3-node HA one (fsn1/nbg1/hel1 + a worker), reached
  by `ssh root@167.233.100.88` with `~/.ssh/id_hetzner` (the old
  `95.217.171.250` gateway is stale → its nginx `502`s). There, the `selenium`
  **Grid container is healthy and serving sessions**, but the `selenium-api`
  (`:8105`) and `dd-browser-test-server` containers are in CrashLoopBackOff with
  thousands of restarts: `cd /opt/dd-next-1/... : No such file or directory`.
  The `dd-next-runtime` deployments mount a hostPath repo that exists on the
  single AWS node but **not on the Hetzner nodes**, so the Maven self-build
  never runs. Fix is a platform change (put the repo on the Hetzner nodes, or
  switch these deployments to a prebuilt image) — out of scope for zed.
- **zed UI through the grid — verified end-to-end on AWS.** The in-memory zed
  stack was deployed into the AWS cluster (namespace `zed-e2e-remote`, ClusterIP)
  and driven from the grid over ClusterDNS
  (`http://dd-zed-web-server.zed-e2e-remote.svc.cluster.local:8081`).
  `dd-browser-test-server` ran the home page, HTMX live search (returned the
  seeded `acme/logkit`), and the package page (rendered `zed add acme/http-kit`)
  through **all three** back-ends, and the **dedicated `dd-selenium-server`**
  rendered the package page too — all `ok:true`, 0 page errors. Teardown removed
  the namespace and the node artifacts.

  Getting there settled the image-distribution question the hard way, since every
  low-touch path was closed (ghcr push needs `write:packages`, the node's role
  can't read the `dd-img-xfer` bucket, SSH `:22` is SG-blocked, ngrok's account is
  suspended). The route that worked, and is the documented one:
  1. **Cross-build for the node's arch.** The images must be `linux/amd64` (the
     AWS node); an arm64 build imports but won't run
     (`ctr: no match for platform`). `docker buildx build --platform linux/amd64
     --output type=docker,dest=...`.
  2. **Transfer over the kube API, import with `ctr`.** `kubectl cp` the gzipped
     tar into a throwaway pod that hostPath-mounts the node's `/tmp`, then (via
     SSM Run Command, since SSH is blocked) `zcat … | ctr -n k8s.io images
     import -`. Deploy with `imagePullPolicy: Never`.
  3. **Seed** through a `kubectl port-forward` of the api + the local `zed` CLI.
  The runner (`cluster/remote-grid.sh`) drove the whole thing; keep it pointed at
  whatever cluster-reachable URL the zed web UI has.
