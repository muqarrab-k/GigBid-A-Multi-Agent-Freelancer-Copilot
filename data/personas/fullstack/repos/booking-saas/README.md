# Booking platform for fitness studios

White-label class booking app for fitness studios. Each studio has its own subdomain, timetable, and memberships.

## Setup

Install dependencies and configure the environment for Next.js, Node.js, PostgreSQL, Prisma, and Stripe.

1. Install packages
2. Set database connection and Stripe credentials
3. Run Prisma migrations
4. Start the app

## Usage

```bash
npm install
npx prisma migrate dev
npm run dev
```

API behavior:
- `src/pages/api/bookings.ts` books a class only when capacity is available
- booking requests are scoped to the current studio
- `src/lib/stripe.ts` creates a checkout session for a membership and handles the Stripe webhook

## Notes

- `prisma/schema.prisma` defines `Studio`, `ClassSession`, `Booking`, and `Membership`
- each model includes `studioId`
- the codebase is set up around studio-scoped data access
- Stripe is used for membership checkout and webhook handling
- the repository covers class booking and membership flows for studio-specific deployments
