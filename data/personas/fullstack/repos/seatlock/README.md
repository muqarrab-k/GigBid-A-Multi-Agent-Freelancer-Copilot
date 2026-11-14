# seatlock

Event ticketing with interactive seat maps and timed seat holds during checkout.

## Setup

Install dependencies and configure the required services for Next.js, Node.js, PostgreSQL, Redis, and Stripe.

## Usage

```bash
npm install
npm run dev
```

`src/seats.ts` handles seat holds and releases in Redis with `SET NX` and an 8 minute expiry.

`src/routes/checkout.ts` confirms held seats after Stripe payment succeeds.

## Notes

Built for an events ticket shop with seat maps. The flow is designed to keep a seat reserved while the buyer completes payment, then finalize the booking only after payment confirmation.

The repository centers on two pieces of logic:
- temporary seat reservation in Redis
- checkout confirmation after successful Stripe payment

This approach was used to support high-volume opening-night sales without duplicate seat assignment.
