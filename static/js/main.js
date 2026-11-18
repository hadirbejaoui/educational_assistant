// Fait disparaître les messages de succès après 5 secondes.
document.querySelectorAll(".alert-success").forEach((alertBox) => {
    setTimeout(() => alertBox.remove(), 5000);
});
// Indicateur de chargement : désactive le bouton pendant un traitement IA.
document.querySelectorAll("form[data-loading]").forEach((form) => {
    form.addEventListener("submit", () => {
        const button = form.querySelector("button[type=submit]");
        if (button) {
            button.disabled = true;
            button.textContent = form.dataset.loading;
        }
    });
});