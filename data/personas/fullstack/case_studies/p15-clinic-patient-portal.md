# Clinic Patient Portal

From September 2024 to January 2025, I worked hourly with a client in healthcare (name withheld) to help them move more of their day-to-day patient workflows into one place. Their team needed a better way to handle booking, share lab results, and keep patients informed without adding more manual follow-up for staff.

I built a patient portal using Next.js, NestJS, PostgreSQL, Prisma, and Twilio. The portal lets patients book appointments, view lab results, and receive SMS reminders. I also made sure every record view is written to a trail of changes, so the client’s team can review who accessed what and when. That was important for building trust and giving the team a clearer operational record around sensitive patient activity.

On the implementation side, I worked across the full stack: the frontend experience in Next.js, backend services in NestJS, database modeling in PostgreSQL with Prisma, and SMS delivery through Twilio. I kept the system focused on the core workflows the client wanted to improve, so their staff could rely on a single portal instead of juggling multiple disconnected steps.

A small example of the kind of service wiring I used:

```ts
import { Injectable } from '@nestjs/common';
import { PrismaService } from './prisma.service';

@Injectable()
export class RecordsService {
  constructor(private prisma: PrismaService) {}

  async viewRecord(userId: string, recordId: string) {
    await this.prisma.recordAccess.create({
      data: { userId, recordId, viewedAt: new Date() },
    });
    return this.prisma.record.findUnique({ where: { id: recordId } });
  }
}
```

The results were clear: 11k patients registered in the portal, and no-shows went down 18% after the reminder flow was put in place. Just as important, the client’s team now works with a system that combines patient self-service, automated reminders, and a reliable record of every chart view in one workflow. That has reduced friction for staff and made patient communication much easier to manage.
