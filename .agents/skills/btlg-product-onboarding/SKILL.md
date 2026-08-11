---
name: btlg-product-onboarding
description: Use when adding, publishing, pricing, licensing, or wiring a new Brain Lift Games / BTLG website product, especially a new game. Covers the BTLG product catalog, Payhip checkout/licensing, frontend product and pricing pages, legal pages, SEO metadata, static game assets, tests, and deploy checks.
---

# BTLG Product Onboarding

Use this skill for adding or changing a product on the Brain Lift Games website. Start from the existing repo patterns; do not invent a parallel product registry.

## First Pass

Work in `/home/hod/IdeaProjects/serious/btlg`. Before editing, inspect the closest existing example:

- Paid web game: Dinkel (`dinkel`, `dinkel-pilot`, upgrade offer).
- Extension: AttentionGuard.
- Available-soon game/app: Screwdriver 2026 or Rogue Rocket Riot.
- Books: existing book catalog entries and pricing cards.

Collect these facts before implementing:

- Stable product key/slug, display name, product type, and public route.
- Whether it is free, paid, available soon, demo-only, an upgrade, or a bundle/main product.
- Payhip token, checkout URL, secret env var, and whether one offer grants access to another product.
- External asset repo/path, static URL, screenshots, and whether the public shell is allowed.
- Whether access is gated by BTLG login/license, game runtime checks, or both.
- Required legal, SEO, pricing, sitemap, and post-deploy checks.

If any high-impact fact is missing, ask for it before wiring payment or access-control behavior.

## Product Spine

The catalog is the source of truth. Add products through the current spine:

- Shared model constants:
  - Add checkout URL constants in `shared/src/main/scala/hod/btlg/shared/models/Products.scala` (`CheckoutUrls`) when the product has a payment or buy redirect.
  - Add price constants in `shared/src/main/scala/hod/btlg/shared/models/Prices.scala` when the product appears on pricing/product pages.
  - Use `ProductType.Book`, `ProductType.Game`, `ProductType.App`, or `ProductType.Extension`; browser extensions are `Extension`, not `App`.
- Backend catalog:
  - Add a `BrainLiftProduct` and `ProductMeta` in `backend/src/main/scala/hod/btlg/persistence/Products.scala`.
  - Choose the next stable internal id. Never reuse ids, even for retired products.
  - Set `displayName`, `category`, `productType`, `showInProdHub`, `order`, `landingGroup`, `availableSoon`, `disabled`, `requiresLicense`, and `purchaseUrl` deliberately.
  - Paid products must have `requiresLicense = true` and `purchaseUrl = Some(...)` unless there is a documented reason they do not use BTLG licenses.
- Payhip and licensing:
  - Payhip remains the only payment provider.
  - Add paid offers in `backend/src/main/scala/hod/btlg/services/PayhipProducts.scala`.
  - Use `PayhipOffer(offerKey, token, grantsProductKey, checkoutUrl, requiresProductKey)` when the offer key differs from the product it grants, such as an upgrade.
  - Add the matching secret config entry in `backend/src/main/resources/application.conf`; quote hyphenated config keys.
  - Add the production env var check to `post-deploy-check.sh`.
  - Do not require Payhip tokens or secrets for available-soon products without checkout.

## Website Wiring

Add only the public surfaces the product actually needs:

- Publishing and product copy must never describe a game or any of its content as
  `handcrafted`, `handmade`, or `hand-made`. Do not imply manual production
  provenance; use verifiable mechanics, quantities, and generation methods.

- Pricing:
  - Add or update product cards in `frontend/src/main/scala/hod/btlg/frontend/pages/PricingPage.scala`.
  - Keep prices sourced from `Prices` and buy links sourced from `CheckoutUrls` or `/buy/<offerKey>`.
- Product page:
  - Create or update a dedicated page when the product has its own marketing, screenshots, demo/play button, license entry, or waitlist/news signup.
  - Wire the SPA route in `frontend/src/main/scala/hod/btlg/frontend/Router.scala`.
  - For games, follow Dinkel's route shape (`/games/<slug>`) unless the repo already has a better category pattern.
- Server-side page serving and SEO:
  - Add a `SeoRoute` in `backend/src/main/scala/hod/btlg/seo/PageMeta.scala`.
  - Add route handling in `backend/src/main/scala/hod/btlg/routes/content/ScalaJsRoutes.scala`.
  - Add metadata in `MetaResolver` and localized title/description strings in `SeoMessages`.
  - Update sitemap and structured data code when the page should be indexed.
- Legal:
  - Add product-specific privacy/terms/refund entries in `BusinessPages.scala` when the product collects data, has payments, has product-specific terms, or appears in legal route tests.
  - Update legal review/test lists when adding new public product URLs.
- Static game assets:
  - For external game repos, validate or add expected symlinks under `backend/src/main/resources/static/dev/`.
  - Update `scripts/check-external-game-links.sh` if a new external game link is required.
  - For paid web games, decide whether `/static/dev/<game>/index.html` is public with runtime mode gating, or blocked by resource access middleware. Match Dinkel unless the user says otherwise.

## Tests And Verification

Add focused tests before broad test runs:

- Catalog tests in `ProductsSpec`: product exists, metadata is correct, product groups derive correctly, paid products have Payhip token, checkout URL, internal id, and secret config path.
- Payhip/buy-route tests for paid offers, including upgrade offers when relevant.
- License tests when access is gated: valid product key, wrong-product validation, grant/revoke, duplicate purchase delivery, and compatibility wrapper behavior.
- Route/SEO tests: SPA route status, metadata, sitemap inclusion, structured data where applicable.
- Frontend/E2E tests: pricing card, product page smoke test, legal pages, and any play/demo/license entry flow.
- Static resource access tests if `/static/dev/<game>` behavior changes.

Run the smallest useful checks first, then broaden:

```bash
sbt "backend/testOnly hod.btlg.persistence.ProductsSpec"
sbt "backend/testOnly hod.btlg.routes.saas.BuyRedirectRouteSpec"
sbt backend/test
```

For frontend/product-page work, build and verify through the repo-standard local path:

```bash
./bootlocal.sh
```

For full release confidence, use the repo's all-test scripts:

```bash
./rate2e.sh
./post-deploy-check.sh
```

Do not deploy unless the user explicitly asks.

## Defaults

- New website games default to `ProductType.Game`, `/games/<slug>`, and a catalog key matching the lowercase slug.
- New paid games default to Payhip checkout plus BTLG product licenses.
- Demos should be separate free/ungated surfaces only if the user wants them independently addressable.
- Main products that include sub-products should grant the main product license and have access checks treat that main license as covering included modes/products.
- Upgrade offers should end at the same total price when that is the product intent; model this as separate Payhip offers that grant the target product.
