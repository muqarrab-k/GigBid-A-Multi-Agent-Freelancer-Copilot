# Live fleet dashboard for Ferrylane Freight

I worked with **Ferrylane Freight** on an hourly engagement from **2020-09 to 2020-12** to help their operations team get a real-time view of their fleet.

Before this project, the dispatch process depended on fragmented updates coming in from the field. For a logistics business, that creates avoidable delays: if a truck is off route, running late, or not where it should be, the team needs to see it quickly. Ferrylane Freight needed a dispatcher-facing screen that could turn GPS pings into a live operational picture without forcing the team to refresh or cross-check multiple systems.

I built a **live fleet dashboard** centered on a dispatcher map. The application was built with **React**, **Node.js**, **Socket.IO**, **Redis**, and **Mapbox**. As GPS updates arrived, the backend pushed each truck’s latest position and ETA to the browser so dispatchers could watch movement change in near real time.

A key part of the implementation was making the update flow fast and reliable. I used Node.js to receive incoming position updates, Redis to coordinate event flow, and Socket.IO to stream updates to connected browsers. On the frontend, React and Mapbox were used to render the fleet map and keep the dispatcher view responsive as new data came in.

```js
const io = new Server(httpServer);

redisSub.on("truck:update", (payload) => {
  io.to("dispatchers").emit("truck:update", {
    truckId: payload.truckId,
    lat: payload.lat,
    lng: payload.lng,
    eta: payload.eta
  });
});
```

The result was a dashboard that could track **1,800 trucks live** and get a GPS ping from the field to the screen in **under 2 seconds**. That gave Ferrylane Freight a much clearer view of fleet movement and helped dispatchers respond faster when timing or location changed. For a logistics operation, that kind of visibility is not just convenient — it directly supports better coordination across the day.
