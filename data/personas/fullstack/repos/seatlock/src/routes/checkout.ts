import { Router } from "express";
import Stripe from "stripe";
import { Pool } from "pg";
import Redis from "ioredis";

const router = Router();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", {
  apiVersion: "2024-06-20",
});
const db = new Pool({ connectionString: process.env.DATABASE_URL });
const redis = new Redis(process.env.REDIS_URL || "");

router.post("/checkout/confirm", async (req, res) => {
  const { paymentIntentId, holdId, seatIds } = req.body || {};

  if (!paymentIntentId || !holdId || !Array.isArray(seatIds) || seatIds.length === 0) {
    return res.status(400).json({ error: "Invalid checkout payload" });
  }

  try {
    const intent = await stripe.paymentIntents.retrieve(paymentIntentId);
    if (intent.status !== "succeeded") {
      return res.status(409).json({ error: "Payment not completed" });
    }

    const holdKey = `seat-hold:${holdId}`;
    const holdRaw = await redis.get(holdKey);
    if (!holdRaw) {
      return res.status(409).json({ error: "Seat hold expired" });
    }

    const hold = JSON.parse(holdRaw);
    if (!Array.isArray(hold.seatIds) || seatIds.some((id: string) => !hold.seatIds.includes(id))) {
      return res.status(400).json({ error: "Seat selection mismatch" });
    }

    const client = await db.connect();
    try {
      await client.query("BEGIN");
      for (const seatId of seatIds) {
        await client.query(
          `UPDATE seats
           SET status = 'sold', stripe_payment_intent_id = $1, updated_at = NOW()
           WHERE id = $2 AND status = 'held'`,
          [paymentIntentId, seatId]
        );
      }
      await client.query("COMMIT");
    } catch (err) {
      await client.query("ROLLBACK");
      throw err;
    } finally {
      client.release();
    }

    await redis.del(holdKey);
    return res.json({ ok: true });
  } catch (error) {
    return res.status(500).json({ error: "Unable to confirm checkout" });
  }
});

export default router;
