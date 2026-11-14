import { Server as HttpServer } from "http";
import { Server as SocketServer, Socket } from "socket.io";
import { createClient, RedisClientType } from "redis";

type GpsPing = {
  truckId: string;
  region: string;
  lat: number;
  lng: number;
  etaMinutes?: number;
  heading?: number;
  speedKph?: number;
  timestamp?: number;
};

let io: SocketServer | null = null;
let redisSub: RedisClientType | null = null;

const regionRooms = new Map<string, Set<string>>();

function roomName(region: string) {
  return `region:${region}`;
}

async function handleGpsMessage(message: string) {
  if (!io) return;

  let ping: GpsPing;
  try {
    ping = JSON.parse(message);
  } catch {
    return;
  }

  if (!ping.region || !ping.truckId) return;

  // Broadcast only to sockets watching this region
  io.to(roomName(ping.region)).emit("truck:update", ping);
}

export async function initSocketServer(httpServer: HttpServer) {
  io = new SocketServer(httpServer, {
    cors: { origin: "*" },
  });

  redisSub = createClient({ url: process.env.REDIS_URL });
  await redisSub.connect();
  await redisSub.subscribe("gps:pings", handleGpsMessage);

  io.on("connection", (socket: Socket) => {
    socket.on("region:watch", (region: string) => {
      if (!region) return;
      socket.join(roomName(region));

      const watchers = regionRooms.get(region) ?? new Set<string>();
      watchers.add(socket.id);
      regionRooms.set(region, watchers);
    });

    socket.on("region:unwatch", (region: string) => {
      if (!region) return;
      socket.leave(roomName(region));

      const watchers = regionRooms.get(region);
      watchers?.delete(socket.id);
      if (watchers && watchers.size === 0) regionRooms.delete(region);
    });

    socket.on("disconnect", () => {
      for (const [region, watchers] of regionRooms.entries()) {
        watchers.delete(socket.id);
        if (watchers.size === 0) regionRooms.delete(region);
      }
    });
  });

  return io;
}

export async function closeSocketServer() {
  await redisSub?.quit();
  redisSub = null;
  io?.close();
  io = null;
}
