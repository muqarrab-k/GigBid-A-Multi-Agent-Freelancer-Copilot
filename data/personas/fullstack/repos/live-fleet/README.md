# Live fleet dashboard

Dispatcher map that streams truck positions and ETAs to the browser as GPS pings arrive.

## Setup

Install dependencies in both the server and client packages, then configure the Redis connection used by the Socket.IO server.

## Usage

```bash
# start the Socket.IO server
npm run start:server

# start the React client
npm run start:client
```

The server listens for GPS updates on Redis, groups truck updates by region, and emits socket events. The client uses `useFleet.ts` to keep local map state in sync with incoming truck position events.

## Notes

- `server/socket.ts` contains the Socket.IO server entrypoint.
- It subscribes to the Redis GPS channel and pushes truck updates to connected browsers.
- `client/useFleet.ts` is the React hook that stores truck positions from socket events.
- The stack is React, Socket.IO, Node.js, Redis, and Mapbox.
- Built for a logistics dashboard where live movement and ETA need to stay current in the UI.
