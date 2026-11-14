Subscription box billing backend for migrating legacy subscribers to Stripe Billing and handling failed payment retries.

## Setup
Install dependencies and configure PostgreSQL and Stripe Billing credentials in your environment.

```bash
npm install
npm run start:dev
```

## Usage
The NestJS service in `src/billing/billing.service.ts` maps legacy plans to Stripe prices and creates subscriptions.

The BullMQ processor in `src/jobs/dunning.processor.ts` runs scheduled retry attempts for failed invoices and sends customer email notifications.

Typical flow:
1. Load the old plan mapping.
2. Create or update the Stripe subscription.
3. Let the retry queue handle failed card payments on schedule.

## Notes
- Built with Node.js, NestJS, PostgreSQL, Stripe Billing, and BullMQ.
- The codebase supports a migration off a legacy plugin and into Stripe-managed subscriptions.
- Around 6.5k subscribers were moved through the migration path.
- Recovery from failed payments improved by about one-third.
