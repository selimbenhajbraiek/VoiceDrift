/* Sign in (/login) and create an account (/signup): one form, two modes */
(function () {
  const $ = (id) => document.getElementById(id);
  let mode = location.pathname === "/signup" ? "signup" : "login";

  function paint() {
    const signup = mode === "signup";
    document.title = `${signup ? "Create account" : "Sign in"} · VoiceDrift`;
    $("form-title").textContent = signup ? "Create your account" : "Sign in";
    $("submit-label").textContent = signup ? "Create account" : "Sign in";
    $("name-field").hidden = !signup;
    $("password").autocomplete = signup ? "new-password" : "current-password";
    $("switch").innerHTML = signup
      ? 'Already have an account? <a class="link" href="/login" data-mode="login">Sign in</a>'
      : 'New here? <a class="link" href="/signup" data-mode="signup">Create an account</a>';
    $("error").textContent = "";
    (signup ? $("name") : $("email")).focus();
  }

  $("switch").addEventListener("click", (e) => {
    const a = e.target.closest("[data-mode]");
    if (!a) return;
    e.preventDefault();
    mode = a.dataset.mode;
    history.replaceState(null, "", `/${mode}`);
    paint();
  });

  $("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const json = { email: $("email").value, password: $("password").value };
    if (mode === "signup") json.name = $("name").value;
    $("submit").disabled = true;
    try {
      await VD.api(`/api/${mode}`, { method: "POST", json });
      location.href = "/dashboard";
    } catch (err) {
      $("error").textContent = err.message;
      $("submit").disabled = false;
    }
  });

  paint();
})();
