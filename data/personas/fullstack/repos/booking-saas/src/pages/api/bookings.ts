import type { NextApiRequest, NextApiResponse } from 'next';
import { prisma } from '../../lib/prisma';

type Data =
  | { bookingId: string }
  | { error: string };

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<Data>
) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { classId, studioId, memberId } = req.body || {};

    if (!classId || !studioId || !memberId) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    // Ensure the class belongs to the current studio
    const classSession = await prisma.classSession.findFirst({
      where: {
        id: classId,
        studioId,
      },
      include: {
        bookings: true,
      },
    });

    if (!classSession) {
      return res.status(404).json({ error: 'Class not found' });
    }

    const currentBookings = classSession.bookings.length;
    if (currentBookings >= classSession.capacity) {
      return res.status(409).json({ error: 'Class is full' });
    }

    // Prevent duplicate bookings for the same member
    const existingBooking = await prisma.booking.findFirst({
      where: {
        classId,
        memberId,
        studioId,
      },
    });

    if (existingBooking) {
      return res.status(409).json({ error: 'Already booked' });
    }

    const booking = await prisma.booking.create({
      data: {
        classId,
        memberId,
        studioId,
        status: 'confirmed',
      },
    });

    return res.status(201).json({ bookingId: booking.id });
  } catch (error) {
    return res.status(500).json({ error: 'Internal server error' });
  }
}
