# Multilingual docs that the engineering team can keep updating

In May 2025, I worked with **Gridbeam Robotics** on a fixed-scope engagement to rebuild their documentation experience around how their engineers actually work. They needed a site that could serve customers in multiple languages without creating a publishing bottleneck for the team. The existing process made it harder to keep content current, and support was spending too much time answering questions that should have been easy to resolve in the docs.

I built a documentation site with **Next.js**, **MDX**, and **Algolia**. The goal was to make the site fast to browse, easy to search, and simple for engineers to maintain directly. Instead of forcing content through a separate editorial workflow, the engineering team now writes the docs in MDX. That means product and technical updates can move from source code to published documentation with less friction, while the site still presents a polished experience to readers in different languages.

A big part of the work was shaping the structure so the same documentation system could support four languages at launch. I focused on making the content model and navigation predictable, so the team could add and update pages without needing to rethink the whole site each time. Instant search was added through Algolia, which helped readers get to the right article faster and reduced the need to dig through nested pages.

A simplified example of the setup looked like this:

```js
// next.config.js
module.exports = {
  i18n: {
    locales: ["en", "fr", "de", "es"],
    defaultLocale: "en",
  },
  pageExtensions: ["js", "jsx", "mdx"],
};
```

After launch, the site went live in **4 languages**, and Gridbeam Robotics saw **support tickets down 27%**. The bigger change, though, was operational: their engineers now own the documentation more directly, keep it current in the same place they work on the product, and rely on a faster search experience for users who need answers quickly.
