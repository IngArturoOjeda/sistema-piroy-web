// Service worker de la app del panel de administración (alcance: /admin/).
//
// Hace solo lo mínimo para que el navegador ofrezca instalar la app ("Abrir en aplicación"):
// - NO guarda nada en caché: los datos del panel (artículos, usuarios, sesión) van siempre a la red, así nunca
//   se muestra información vieja ni queda nada del administrador guardado en el dispositivo;
// - si no hay conexión al abrir una página del panel, muestra un aviso en lugar del error del navegador.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (evento) => evento.waitUntil(self.clients.claim()));

const PAGINA_SIN_CONEXION = `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sin conexión - AGRO-VETZO</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #FAF7F2; color: #2B1A0A; margin: 0;
         min-height: 100vh; display: flex; align-items: center; justify-content: center; text-align: center; padding: 24px; }
  main { max-width: 380px; }
  h1 { color: #603000; font-size: 1.4rem; margin-bottom: 10px; }
  p { line-height: 1.5; margin-bottom: 18px; }
  button { background: #2E7A12; color: #fff; border: 0; border-radius: 8px; padding: 12px 22px; font-size: 1rem; font-weight: 700; cursor: pointer; }
</style>
</head>
<body>
  <main>
    <h1>Sin conexión</h1>
    <p>No se puede abrir el panel porque no hay internet. Revisá la conexión y volvé a intentar.</p>
    <button type="button" onclick="location.reload()">Reintentar</button>
  </main>
</body>
</html>`;

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  if (peticion.mode !== "navigate") return; // todo lo demás va directo a la red
  evento.respondWith(
    fetch(peticion).catch(() => new Response(PAGINA_SIN_CONEXION, {
      status: 503,
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
    }))
  );
});
