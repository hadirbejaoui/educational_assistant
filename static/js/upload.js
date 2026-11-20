/* Zone de dépôt du formulaire d'import : glisser-déposer + validation côté navigateur.
   Cette validation n'est qu'un confort : le serveur revérifie tout (extension, taille,
   signature PDF) et reste la seule référence. */
(function () {
    "use strict";

    const form = document.querySelector("[data-upload-form]");
    if (!form) return;

    const zone = form.querySelector("[data-dropzone]");
    const input = zone.querySelector("input[type=file]");
    const fileLabel = form.querySelector("[data-dropzone-file]");
    const errorBox = form.querySelector("[data-dropzone-error]");
    const titleInput = form.querySelector("input[name=title]");

    const maxBytes = Number(input.dataset.maxBytes);
    const maxMb = input.dataset.maxMb;
    const extensions = (input.dataset.extensions || "").split(",").filter(Boolean);

    function formatSize(bytes) {
        if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " Mo";
        return Math.max(1, Math.round(bytes / 1024)) + " Ko";
    }

    /** Retourne un message d'erreur, ou "" si le fichier semble acceptable. */
    function checkFile(file) {
        if (!file) return "Choisissez un fichier.";
        const name = file.name.toLowerCase();
        const dot = name.lastIndexOf(".");
        const extension = dot === -1 ? "" : name.slice(dot);
        if (!extensions.includes(extension)) {
            return "Format non autorisé (" + (extension || "sans extension") +
                "). Formats acceptés : " + extensions.join(", ") + ".";
        }
        if (file.size === 0) return "Le fichier est vide.";
        if (maxBytes && file.size > maxBytes) {
            return "Fichier trop volumineux (" + formatSize(file.size) + ", maximum " + maxMb + " Mo).";
        }
        return "";
    }

    function showResult() {
        const file = input.files[0];
        const error = file ? checkFile(file) : "";
        fileLabel.textContent = file ? "Fichier choisi : " + file.name + " (" + formatSize(file.size) + ")" : "";
        errorBox.textContent = error;
        errorBox.hidden = !error;
        zone.classList.toggle("is-invalid", Boolean(error));
        input.setAttribute("aria-invalid", error ? "true" : "false");
        if (file && !error && titleInput && !titleInput.value) {
            titleInput.placeholder = file.name.replace(/\.[^.]+$/, "");
        }
        return error;
    }

    input.addEventListener("change", showResult);

    ["dragenter", "dragover"].forEach((type) => {
        zone.addEventListener(type, (event) => {
            event.preventDefault();
            zone.classList.add("is-dragover");
        });
    });
    ["dragleave", "drop"].forEach((type) => {
        zone.addEventListener(type, () => zone.classList.remove("is-dragover"));
    });
    zone.addEventListener("drop", (event) => {
        event.preventDefault();
        const files = event.dataTransfer.files;
        if (!files.length) return;
        if (files.length > 1) {
            errorBox.textContent = "Déposez un seul fichier à la fois.";
            errorBox.hidden = false;
            return;
        }
        input.files = files; // le fichier déposé devient celui du formulaire
        showResult();
    });

    // Bloque l'envoi d'un fichier manifestement invalide (le serveur vérifiera de toute façon)
    form.addEventListener("submit", (event) => {
        const error = input.files.length ? showResult() : checkFile(null);
        if (error) {
            event.preventDefault();
            errorBox.textContent = error;
            errorBox.hidden = false;
            input.focus();
        }
    }, true); // phase de capture : avant l'indicateur de chargement de main.js
})();
