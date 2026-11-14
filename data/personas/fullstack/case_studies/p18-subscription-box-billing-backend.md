# Subscription box billing backend

In July 2025, I started working with **Fernwood Pantry**, an e-commerce business running a subscription box model that had outgrown its legacy billing setup. Their existing plugin-based approach was creating friction around payments and made it hard to recover failed card charges cleanly. They needed a more dependable system that could support growth without creating more manual work for their team.

I was brought in on an hourly engagement to rebuild the billing flow around **Stripe Billing** and a more maintainable backend. I used **Node.js**, **NestJS**, **PostgreSQL**, and **BullMQ** to move subscriber billing off the old plugin and into a system that could handle payment retries in a controlled way. The goal was not just to replace the old setup, but to make billing more reliable and easier to operate as their subscriber base scaled.

A key part of the work was building a retry queue for failed card payments. Instead of letting failed charges disappear into support tickets and manual follow-up, the backend could pick them up, re-attempt payment, and keep the subscription state in sync. I also structured the database and service layer so the migration from the legacy system could be handled safely and incrementally.

Here’s a simplified example of the kind of queue-driven retry worker I implemented:

```ts
@Processor('payment-retries')
export class PaymentRetryProcessor {
  @Process('retry-card')
  async handle(job: Job<{ subscriptionId: string }>) {
    const { subscriptionId } = job.data;
    const subscription = await this.billingService.getSubscription(subscriptionId);

    if (!subscription) return;

    await this.billingService.retryFailedPayment(subscriptionId);
    await this.billingService.syncSubscriptionState(subscriptionId);
  }
}
```

By the time the project wrapped in October 2025, I had helped **migrate 6.5k subscribers** onto the new billing system. The retry flow also **recovered 31% of failed payments**, which directly improved revenue retention for Fernwood Pantry and reduced the amount of manual intervention needed from their team. The end result was a cleaner billing operation, better payment recovery, and a more scalable foundation for their subscription business.
