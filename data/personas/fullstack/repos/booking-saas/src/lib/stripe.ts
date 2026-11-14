import Stripe from "stripe";
import { NextRequest, NextResponse } from "next/server";

const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
const stripeWebhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

if (!stripeSecretKey) {
  throw new Error("Missing STRIPE_SECRET_KEY");
}

export const stripe = new Stripe(stripeSecretKey, {
  apiVersion: "2024-06-20",
});

export function createCheckoutSession(params: {
  membershipId: string;
  membershipName: string;
  amount: number;
  currency: string;
  successUrl: string;
  cancelUrl: string;
  customerEmail?: string;
  studioId: string;
  subdomain: string;
}) {
  return stripe.checkout.sessions.create({
    mode: "payment",
    customer_email: params.customerEmail,
    success_url: params.successUrl,
    cancel_url: params.cancelUrl,
    line_items: [
      {
        quantity: 1,
        price_data: {
          currency: params.currency,
          unit_amount: params.amount,
          product_data: {
            name: params.membershipName,
            metadata: {
              membershipId: params.membershipId,
              studioId: params.studioId,
              subdomain: params.subdomain,
            },
          },
        },
      },
    ],
    metadata: {
      membershipId: params.membershipId,
      studioId: params.studioId,
      subdomain: params.subdomain,
    },
  });
}

export async function constructWebhookEvent(req: NextRequest) {
  if (!stripeWebhookSecret) {
    throw new Error("Missing STRIPE_WEBHOOK_SECRET");
  }

  const payload = await req.text();
  const signature = req.headers.get("stripe-signature");
  if (!signature) throw new Error("Missing Stripe signature");

  return stripe.webhooks.constructEvent(payload, signature, stripeWebhookSecret);
}

export async function handleStripeWebhook(event: Stripe.Event) {
  switch (event.type) {
    case "checkout.session.completed": {
      const session = event.data.object as Stripe.Checkout.Session;
      return {
        status: "paid",
        sessionId: session.id,
        customerId: session.customer,
        membershipId: session.metadata?.membershipId ?? null,
        studioId: session.metadata?.studioId ?? null,
      };
    }
    default:
      return { status: "ignored", type: event.type };
  }
}

export function webhookResponse(result: unknown) {
  return NextResponse.json(result);
}
