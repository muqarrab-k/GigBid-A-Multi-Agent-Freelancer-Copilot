import { createClient, type RedisClientType } from 'redis';

const REDIS_URL = process.env.REDIS_URL;
const SEAT_HOLD_TTL_SECONDS = 8 * 60;

let redisClient: RedisClientType | null = null;

async function getRedisClient() {
  if (!REDIS_URL) {
    throw new Error('REDIS_URL is not set');
  }

  if (!redisClient) {
    redisClient = createClient({ url: REDIS_URL });
    redisClient.on('error', () => {
      // Let callers handle failures; keep the client reusable.
    });
  }

  if (!redisClient.isOpen) {
    await redisClient.connect();
  }

  return redisClient;
}

function seatKey(eventId: string, seatId: string) {
  return `seatlock:${eventId}:${seatId}`;
}

export async function holdSeat(eventId: string, seatId: string, userId: string) {
  const client = await getRedisClient();
  const key = seatKey(eventId, seatId);

  const result = await client.set(key, userId, {
    NX: true,
    EX: SEAT_HOLD_TTL_SECONDS,
  });

  return result === 'OK';
}

export async function releaseSeat(eventId: string, seatId: string, userId?: string) {
  const client = await getRedisClient();
  const key = seatKey(eventId, seatId);
  const current = await client.get(key);

  // Only release if the caller owns the hold, when provided.
  if (current && userId && current !== userId) {
    return false;
  }

  const removed = await client.del(key);
  return removed > 0;
}

export async function getSeatHold(eventId: string, seatId: string) {
  const client = await getRedisClient();
  return client.get(seatKey(eventId, seatId));
}
