import { useEffect, useMemo, useRef, useState } from 'react';

type TruckPosition = {
  truckId: string;
  lng: number;
  lat: number;
  eta?: number;
  heading?: number;
  updatedAt: number;
};

type SocketLike = {
  on: (event: string, handler: (payload: any) => void) => void;
  off: (event: string, handler: (payload: any) => void) => void;
};

type UseFleetOptions = {
  socket: SocketLike | null;
};

export function useFleet({ socket }: UseFleetOptions) {
  const [positions, setPositions] = useState<Record<string, TruckPosition>>({});
  const positionsRef = useRef(positions);
  positionsRef.current = positions;

  const upsertPosition = useMemo(
    () => (payload: Partial<TruckPosition> & { truckId: string; lng: number; lat: number }) => {
      setPositions((prev) => ({
        ...prev,
        [payload.truckId]: {
          truckId: payload.truckId,
          lng: payload.lng,
          lat: payload.lat,
          eta: payload.eta,
          heading: payload.heading,
          updatedAt: payload.updatedAt ?? Date.now(),
        },
      }));
    },
    []
  );

  useEffect(() => {
    if (!socket) return;

    const onPing = (payload: any) => {
      if (!payload || !payload.truckId) return;
      upsertPosition(payload);
    };

    const onBatch = (payload: any[]) => {
      if (!Array.isArray(payload)) return;
      for (const item of payload) onPing(item);
    };

    socket.on('truck:position', onPing);
    socket.on('fleet:positions', onBatch);

    // Reset stale map state when the connection drops.
    return () => {
      socket.off('truck:position', onPing);
      socket.off('fleet:positions', onBatch);
    };
  }, [socket, upsertPosition]);

  const sortedTrucks = useMemo(
    () =>
      Object.values(positions).sort((a, b) => {
        if (a.updatedAt !== b.updatedAt) return b.updatedAt - a.updatedAt;
        return a.truckId.localeCompare(b.truckId);
      }),
    [positions]
  );

  return {
    positions,
    sortedTrucks,
    latestCount: sortedTrucks.length,
    hasTrucks: sortedTrucks.length > 0,
  };
}
