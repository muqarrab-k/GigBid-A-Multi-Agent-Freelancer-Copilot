# Home goods storefront rebuild

In early 2021, I worked with **Juniper & Ash Home** on a fixed-scope rebuild of their storefront. Their existing theme-based shop had become slow and rigid, and the marketing team had to depend on developers for routine content updates. The goal was to replace that setup with something faster, easier to maintain, and more flexible for day-to-day merchandising.

I rebuilt the store as a headless storefront using **Next.js**, **Tailwind CSS**, **Sanity**, **Stripe**, and **Vercel**. My focus was on creating a front end that loaded quickly, supported strong organic discoverability, and gave the team full control over content without touching code. I separated presentation from content so product pages, editorial blocks, and landing pages could be edited in Sanity while the storefront remained fast and stable.

A key part of the work was shaping the rendering strategy so pages could arrive with meaningful content already in place, rather than waiting for everything to load client-side. That helped the site perform better on slower connections and gave search crawlers a cleaner version of each page. I also tightened the checkout flow with Stripe and kept the UI lightweight with Tailwind to reduce visual and performance overhead.

Example of the deployment setup:

```js
// next.config.js
module.exports = {
  reactStrictMode: true,
  images: {
    formats: ['image/avif', 'image/webp'],
  },
  env: {
    SANITY_PROJECT_ID: process.env.SANITY_PROJECT_ID,
    STRIPE_PUBLIC_KEY: process.env.STRIPE_PUBLIC_KEY,
  },
}
```

The rebuild made a clear difference. The largest contentful paint improved from **4.1s to 1.3s**, and **organic traffic increased by 38% in 3 months**. Just as importantly, the marketing team could update the storefront themselves, which removed a recurring bottleneck and made the site easier to evolve after launch.

For me, this project was a good example of how a modern React and Next.js stack can solve both speed and workflow problems at once: a cleaner architecture for developers, and a much more usable system for the people managing the store every day.
