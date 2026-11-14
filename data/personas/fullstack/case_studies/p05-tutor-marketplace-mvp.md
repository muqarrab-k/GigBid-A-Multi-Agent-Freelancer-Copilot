# Tutor marketplace MVP for Brightpath Tutors

Brightpath Tutors needed a fast way to launch an edtech marketplace that could connect students with tutors, support online lessons, and handle payments cleanly from day one. I joined on a fixed engagement in October 2021 and helped build the MVP through February 2022, with the goal of getting something reliable live quickly without sacrificing the core product flow.

I built the application as a two-sided marketplace using Next.js for the frontend and Node.js for the backend, with MongoDB for persistence. The product centered on tutor profiles, lesson booking, live video sessions, and automated money flow between students, Brightpath Tutors, and tutors. A big part of the technical work was making the booking and payment journey feel seamless while keeping the system straightforward enough to iterate on during launch.

For the live lesson experience, I integrated Twilio Video so students and tutors could join sessions directly in the app. On the payments side, I worked with Stripe Connect to route funds and support tutor earnings in a way that fit the marketplace model. I also designed the data layer and API interactions so profile data, bookings, and session states stayed consistent across the app.

A simplified example of the kind of server-side integration used in the stack:

```js
import Stripe from "stripe";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

export async function createConnectedAccount(email) {
  const account = await stripe.accounts.create({
    type: "express",
    country: "US",
    email,
  });

  return account.id;
}
```

The MVP went live in 11 weeks. By the first quarter after launch, Brightpath Tutors had 300 tutors on the platform and $48k in gross bookings. For me, the project was a strong example of shipping a focused marketplace product quickly, with the backend and transaction flow built carefully enough to support real usage from the start.
