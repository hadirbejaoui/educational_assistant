// Fait disparaître les messages de succès après 5 secondes.
document.querySelectorAll(".alert-success").forEach((alertBox) => {
    setTimeout(() => alertBox.remove(), 5000);
});