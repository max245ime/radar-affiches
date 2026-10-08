const C="radar-v2",SHELL=["./","index.html","manifest.json","icon-192.png"];
self.addEventListener("install",e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)));self.skipWaiting()});
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C).map(x=>caches.delete(x)))).then(()=>clients.claim())));
self.addEventListener("fetch",e=>{const u=new URL(e.request.url);if(u.origin!==location.origin)return;
 if(u.pathname.endsWith("data.json")||u.pathname.endsWith("push-config.json")){e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(C).then(x=>x.put(e.request,c));return r}).catch(()=>caches.match(e.request)))}
 else e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)))});
self.addEventListener("push",e=>e.waitUntil((async()=>{
 let m={title:"🎬 Radar Affiches",body:"Nouvelle alerte : ouvre l'app.",url:"./"};
 try{const cfg=await (await fetch("push-config.json?"+Date.now())).json();const r=await fetch(cfg.url+"/last?"+Date.now(),{cache:"no-store"});if(r.ok)m=await r.json()}catch(_){}
 await self.registration.showNotification(m.title,{body:m.body,icon:"icon-192.png",badge:"icon-192.png",tag:"radar",renotify:true,requireInteraction:true,vibrate:[200,100,200],data:{url:m.url||"./"}})})()));
self.addEventListener("notificationclick",e=>{e.notification.close();const u=e.notification.data?.url||"./";
 e.waitUntil(clients.matchAll({type:"window",includeUncontrolled:true}).then(l=>l.length?l[0].focus():clients.openWindow(u)))});
