# Release & Verification Checklist

> [!IMPORTANT]
> **Git Operation Policy Reminder:**
> Tagging, merging to `main`, and pushing release commits require explicit human approval and should be executed personally by the repository maintainer.

This checklist outlines the formal verification and release procedure for tagging **`v1.0.0-portfolio-mvp`**.

---

## Pre-Release Verification Checklist

### 1. Full Local Regression Test Run
Run the complete multi-module focused regression test suite covering all implemented use cases (UC-12 through UC-23):

```powershell
python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d salla_test `
  -u ecommerce_connector_base,ecommerce_salla_connector `
  --test-enable `
  --test-tags /ecommerce_connector_base:TestUC12SaleOrderIdempotency,`
/ecommerce_connector_base:TestUC13ManualRetry,`
/ecommerce_connector_base:TestUC18StockReadiness,`
/ecommerce_connector_base:TestUC19ReportingManagerViews,`
/ecommerce_salla_connector:TestUC12WebhookIdempotency,`
/ecommerce_salla_connector:TestUC13WebhookRetry,`
/ecommerce_salla_connector:TestUC14OrderStatusUpdates,`
/ecommerce_salla_connector:TestUC15OAuthAuthorization,`
/ecommerce_salla_connector:TestUC15ControllerRedaction,`
/ecommerce_salla_connector:TestUC16TokenRefresh,`
/ecommerce_salla_connector:TestUC17SallaAPIEnrichment,`
/ecommerce_salla_connector:TestSallaLivePayloadCompatibility,`
/ecommerce_salla_connector:TestUC20DemoDataBootstrap,`
/ecommerce_salla_connector:TestUC24OrderCancellation `
  --stop-after-init --no-http --log-level=error
```
*Requirement:* Exit code `0` with all test suites passing.

### 2. Static Code & Syntax Compilation
Run byte-compilation and git whitespace gate:

```powershell
python -m compileall ecommerce_connector_base ecommerce_salla_connector
git diff --check
```
*Requirement:* Exit code `0` for both commands.

### 3. Merge Feature Branch to `develop`
- Review the proposed feature branch diff and commit message.
- Merge the feature branch into `develop` and push to `origin/develop`.

### 4. GitHub Actions CI Verification
- Verify both workflows pass on GitHub:
  - `static-checks` (bytecode compile, XML/JSON parsing, whitespace gate)
  - `odoo-tests` (Odoo 18 container regression run)

### 5. Main Release Merge & Tagging
Execute the release merge and create the annotated portfolio release tag:

```powershell
git checkout main
git pull origin main
git merge develop --no-ff -m "Release v1.0.0-portfolio-mvp"
git tag -a v1.0.0-portfolio-mvp -m "Release v1.0.0-portfolio-mvp: Odoo 18 E-commerce Sales Sync (Salla MVP)"
git push origin main --tags
```

### 6. Clean Database Sanity & Demo Data Bootstrap
On a fresh demo-enabled database:
- Install both modules:
  ```powershell
  python C:\odoo18\odoo-bin -c C:\odoo18\conf\odoo.conf -d fresh_demo_db -i ecommerce_connector_base,ecommerce_salla_connector --stop-after-init
  ```
- Verify "UC-20 Demo Salla Store" and sample records are created automatically.
- Re-run module update (`-u ecommerce_connector_base,ecommerce_salla_connector`) to verify demo data bootstrap is idempotent (0 duplicates created).

### 7. Portfolio Visuals
- Capture portfolio screenshots according to [docs/13_SCREENSHOT_GUIDE.md](13_SCREENSHOT_GUIDE.md).
