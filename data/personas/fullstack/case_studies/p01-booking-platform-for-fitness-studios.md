# White-label booking platform for Pulsebox Studios

In 2020, I worked with **Pulsebox Studios** on a fixed-scope build for a booking platform aimed at fitness studios. They needed a product that could support many studios under one system while still giving each location its own branded experience, timetable, and membership flow. The main challenge was to keep the platform flexible enough for different studio setups without making the codebase hard to maintain.

I built the application with **Next.js**, **Node.js**, **PostgreSQL**, **Prisma**, and **Stripe**. My focus was on designing a structure that could serve each studio from its own subdomain while keeping shared logic centralized. On the frontend, I used Next.js to render the studio experience cleanly and consistently. On the backend, Node.js handled the booking, membership, and checkout workflows, while PostgreSQL stored the core data model. Prisma helped keep the database layer predictable as the platform grew.

A big part of the work was making sure the app could identify the active studio from the incoming host name and load the correct timetable, branding, and membership configuration. I also wired the checkout flow through Stripe so studios could sell memberships directly through the platform.

Here’s a simplified example of the kind of host-based routing logic I used:

```js
export async function getServerSideProps({ req }) {
  const host = req.headers.host;
  const subdomain = host.split('.')[0];

  const studio = await prisma.studio.findUnique({
    where: { subdomain },
    include: { memberships: true, timetable: true }
  });

  return {
    props: {
      studio,
    },
  };
}
```

The result was a white-label system that Pulsebox Studios could roll out across multiple fitness studios with a consistent technical foundation. Over the first six months, **64 studios onboarded**, and the checkout flow reached **71% conversion**. For me, the project was a strong example of building a scalable product architecture while still delivering a polished, studio-specific experience end to end.
