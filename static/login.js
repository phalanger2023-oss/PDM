// Page de connexion : envoie l'identifiant et le mot de passe au serveur (Python), qui vérifie et pose le cookie.
const $ = (id) => document.getElementById(id);

// La durée de connexion mémorisée est un réglage du serveur : on l'affiche telle quelle
fetch("/api/me").then((r) => r.json()).then((m) => { if (m.days) $("days").textContent = m.days; }).catch(() => {});

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("err"), go = $("go");
  err.hidden = true;
  go.disabled = true;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("user").value.trim(), password: $("pw").value, remember: $("remember").checked }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) { location.replace("/"); return; }
    err.textContent = data.error || "Connexion impossible.";
  } catch (ex) {
    err.textContent = "Le serveur ne répond pas. Réessayez dans un instant.";
  }
  err.hidden = false;
  go.disabled = false;
  $("pw").select();
});
