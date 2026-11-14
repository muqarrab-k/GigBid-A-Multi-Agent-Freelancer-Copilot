# Restaurant ordering web app for Saffron Lane Kitchens

In early 2023, I worked with **Saffron Lane Kitchens**, a food and beverage business running **9 restaurants**, on a fixed engagement to improve how customers could place orders online. Their existing ordering flow needed to stay usable even when connections were unreliable, especially during busy periods and in locations where mobile signal was inconsistent. The business goal was simple: make ordering easier, more dependable, and more likely to convert into real sales.

I built an installable ordering app using **React**, **Vite**, **Firebase**, **Stripe**, and **Workbox**. My focus was on creating an experience that would keep the menu and cart available even when the network dropped out, so customers could continue browsing, building orders, and checking out without starting over. I also made sure the app felt natural to return to by supporting installation on devices, giving the ordering flow a more app-like presence.

A big part of the work was making the front end resilient. I structured the app so the core ordering screens were fast to load and the most important interactions stayed usable under weak connectivity. I also integrated Stripe for payments and Firebase for the app’s backend needs, keeping the implementation lean while still supporting a production-ready ordering flow across multiple restaurants.

Here’s a small example of the kind of setup I used for the installable app behavior:

```js
export default {
  name: "Saffron Lane Kitchens Ordering",
  short_name: "SLK Orders",
  start_url: "/",
  display: "standalone",
  background_color: "#ffffff",
  theme_color: "#111111",
  icons: [
    { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
    { src: "/icon-512.png", sizes: "512x512", type: "image/png" }
  ]
};
```

The result was a smoother ordering experience that clearly mattered to the business. Within two months, **22% of orders came through the app**, showing that customers were willing to adopt the new channel quickly. For Saffron Lane Kitchens, that meant the product wasn’t just a technical improvement — it became a meaningful part of how people placed orders across their restaurants.
