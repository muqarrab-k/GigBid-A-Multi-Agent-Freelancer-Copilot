# Staff onboarding portal

In 2021, I worked with a client in healthcare staffing (name withheld) to replace a slow, manual onboarding process with something their team could actually run day to day. Nurses were uploading credentials through scattered email threads and shared files, while managers had to chase approvals across regions. The goal was to give everyone one internal place to handle onboarding, with clear permissions based on region and responsibility.

I built an internal portal that let nurses upload their credentials and supporting paperwork, and let managers review and approve submissions inside the same workflow. Because the client operates across multiple regions, I designed the access model so people only saw the staff and approvals relevant to their territory. That kept the process organized and reduced the back-and-forth that had been slowing things down.

The stack included React, NestJS, PostgreSQL, TypeORM, and Auth0. I used React for the portal interface, NestJS for the backend workflow, PostgreSQL for the data layer, and TypeORM to keep the persistence code maintainable. Auth0 handled authentication, which made it easier for the client’s team to log in securely and work within their assigned scope.

A simple example of the permission pattern looked like this:

```ts
const canReview = (userRegion: string, staffRegion: string, isManager: boolean) =>
  isManager && userRegion === staffRegion;

if (canReview(user.region, staff.region, user.isManager)) {
  return approveSubmission(staff.id);
}
```

The impact was immediate. The portal ended up supporting 2,400 staff, and onboarding paperwork dropped from 5 days to 1 day. Just as importantly, the client’s team now works from a single system instead of stitching together emails and manual follow-ups. Managers can review incoming documents faster, nurses know where to submit their materials, and regional teams can keep onboarding moving without constant coordination overhead.

This project was an hourly engagement from 2021-05 to 2021-09, and it’s a good example of how I like to build internal tools: practical, structured, and tailored to how the team already works.
