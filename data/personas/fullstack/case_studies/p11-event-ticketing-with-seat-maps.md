# Event ticketing with seat maps

In late 2023, I worked with **Northlight Events** on a fixed-scope build for their event ticketing flow. Their challenge was straightforward but demanding: they needed a ticket shop that could handle high demand without overselling seats, while giving buyers a clear, interactive way to choose exactly where they wanted to sit.

I built the experience in **Next.js** with a **Node.js** backend and **PostgreSQL** for the core booking data. The main feature was an interactive seat map that let buyers browse availability, pick seats, and move through checkout with confidence. Because seats could not be sold twice, I designed the flow so a selected seat would be reserved for **8 minutes** while the buyer completed payment. That reservation window had to be reliable under pressure, especially when many people were checking out at the same time.

To make that work, I used **Redis** alongside PostgreSQL to manage short-lived seat holds efficiently. The backend was structured to verify availability before confirming a purchase, and Stripe handled the payment step. The system needed to keep the seat map responsive while also protecting the booking data from race conditions during busy moments. I focused on keeping the reservation logic tight, predictable, and easy to reason about.

```ts
// seat hold flow
const holdKey = `hold:${eventId}:${seatId}`;
const ttlSeconds = 8 * 60;

const acquired = await redis.set(holdKey, userId, {
  NX: true,
  EX: ttlSeconds,
});

if (!acquired) throw new Error("Seat already held");

await db.query(
  "insert into seat_holds(event_id, seat_id, user_id, expires_at) values ($1,$2,$3, now() + interval '8 minutes')",
  [eventId, seatId, userId]
);
```

The result was a ticketing platform that performed well on launch and held up under real demand. On opening night, **18k tickets were sold**, and there were **zero double-booked seats**. For Northlight Events, that meant a smooth buying experience for customers and a booking system they could trust when it mattered most.
