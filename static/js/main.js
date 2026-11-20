/* Comportements communs à toutes les pages (JavaScript classique, sans framework). */
(function () {
    "use strict";

    const DESKTOP = window.matchMedia("(min-width: 992px)"); // même seuil que layout.css

    /* ---------- Barre latérale en tiroir (< 992 px) ---------- */
    const sidebar = document.querySelector("[data-sidebar]");
    const toggle = document.querySelector("[data-sidebar-toggle]");
    const closeButton = document.querySelector("[data-sidebar-close]");
    const overlay = document.querySelector("[data-sidebar-overlay]");

    function focusables() {
        return Array.from(sidebar.querySelectorAll("a[href], button:not([disabled])"))
            .filter((element) => element.offsetParent !== null);
    }

    function isOpen() {
        return sidebar.classList.contains("is-open");
    }

    function openSidebar() {
        sidebar.classList.add("is-open");
        overlay.hidden = false;
        toggle.setAttribute("aria-expanded", "true");
        document.body.classList.add("has-drawer-open"); // la page ne défile pas derrière le tiroir
        const current = sidebar.querySelector("[aria-current='page']") || focusables()[0];
        if (current) current.focus();
    }

    function closeSidebar(returnFocus) {
        if (!isOpen()) return;
        sidebar.classList.remove("is-open");
        overlay.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
        document.body.classList.remove("has-drawer-open");
        if (returnFocus) toggle.focus(); // le focus revient au bouton qui a ouvert le menu
    }

    if (sidebar && toggle && overlay) {
        toggle.addEventListener("click", () => (isOpen() ? closeSidebar(true) : openSidebar()));
        overlay.addEventListener("click", () => closeSidebar(true));
        if (closeButton) closeButton.addEventListener("click", () => closeSidebar(true));

        // Un lien cliqué ferme le tiroir
        sidebar.addEventListener("click", (event) => {
            if (event.target.closest("a") && !DESKTOP.matches) closeSidebar(false);
        });

        document.addEventListener("keydown", (event) => {
            if (!isOpen()) return;
            if (event.key === "Escape") {
                closeSidebar(true);
                return;
            }
            // Piégeage du focus : Tab reste dans le tiroir tant qu'il est ouvert
            if (event.key === "Tab") {
                const items = focusables();
                if (!items.length) return;
                const first = items[0];
                const last = items[items.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault();
                    last.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault();
                    first.focus();
                }
            }
        });

        // Passer en grand écran referme le tiroir
        DESKTOP.addEventListener("change", (query) => {
            if (query.matches) closeSidebar(false);
        });
    }

    /* ---------- Alertes ---------- */
    document.querySelectorAll("[data-dismiss-alert]").forEach((button) => {
        button.addEventListener("click", () => button.closest(".alert").remove());
    });
    // Les succès disparaissent seuls ; les erreurs restent jusqu'à ce qu'on les ferme
    document.querySelectorAll(".alert-success").forEach((alertBox) => {
        setTimeout(() => alertBox.remove(), 6000);
    });

    /* ---------- Confirmation avant une action destructrice ---------- */
    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm(form.dataset.confirm)) event.preventDefault();
        });
    });

    /* ---------- Onglets (résumés) : sans JS, tous les panneaux restent visibles ---------- */
    document.querySelectorAll("[data-tabs]").forEach((tabs, tabsIndex) => {
        const panels = Array.from(tabs.querySelectorAll("[data-tab-panel]"));
        if (panels.length < 2) return;
        const list = document.createElement("div");
        list.className = "tabs__list";
        list.setAttribute("role", "tablist");

        const buttons = panels.map((panel, index) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "tabs__tab";
            button.id = "tab-" + tabsIndex + "-" + index;
            button.textContent = panel.dataset.tabLabel;
            button.setAttribute("role", "tab");
            button.setAttribute("aria-controls", panel.id);
            panel.setAttribute("role", "tabpanel");
            panel.setAttribute("aria-labelledby", button.id);
            button.addEventListener("click", () => select(index, false));
            list.appendChild(button);
            return button;
        });

        function select(index, moveFocus) {
            buttons.forEach((button, i) => {
                const active = i === index;
                button.setAttribute("aria-selected", String(active));
                button.tabIndex = active ? 0 : -1;
                panels[i].hidden = !active;
            });
            if (moveFocus) buttons[index].focus();
        }

        // Flèches gauche/droite pour passer d'un onglet à l'autre
        list.addEventListener("keydown", (event) => {
            const current = buttons.indexOf(document.activeElement);
            if (current === -1) return;
            if (event.key === "ArrowRight") select((current + 1) % buttons.length, true);
            if (event.key === "ArrowLeft") select((current - 1 + buttons.length) % buttons.length, true);
        });

        tabs.prepend(list);
        tabs.classList.add("is-enhanced");
        select(0, false);
    });

    /* ---------- Indicateur des traitements longs ---------- */
    const SLOW_AFTER_SECONDS = 90;

    function formatDuration(seconds) {
        const minutes = Math.floor(seconds / 60);
        const rest = String(seconds % 60).padStart(2, "0");
        return minutes ? minutes + " min " + rest + " s" : seconds + " s";
    }

    function showLoading(form) {
        const status = document.createElement("div");
        status.className = "loading-status";
        status.setAttribute("role", "status");
        status.setAttribute("aria-live", "polite");
        status.dataset.loadingStatus = "";

        const spinner = document.createElement("span");
        spinner.className = "spinner";
        spinner.setAttribute("aria-hidden", "true");
        const text = document.createElement("p");
        const label = document.createElement("strong");
        label.textContent = form.dataset.loading;
        const timer = document.createElement("span");
        const hint = document.createElement("span");
        hint.textContent = " Gardez cette page ouverte.";
        text.append(label, " ", timer, hint);
        status.append(spinner, text);

        // Sous le groupe de boutons s'il existe, sinon sous le formulaire
        const anchor = form.closest(".cluster, .page-header__actions, .card__header") || form;
        anchor.insertAdjacentElement("afterend", status);

        const started = Date.now();
        const tick = () => {
            const elapsed = Math.round((Date.now() - started) / 1000);
            timer.textContent = "(" + formatDuration(elapsed) + ")";
            if (elapsed >= SLOW_AFTER_SECONDS && !status.classList.contains("is-slow")) {
                status.classList.add("is-slow");
                hint.textContent =
                    " C'est plus long que d'habitude : le traitement continue sur le serveur. " +
                    "Ne rechargez pas la page ; un message d'erreur s'affichera si le délai est dépassé.";
            }
        };
        tick();
        status.dataset.timer = String(setInterval(tick, 1000));
    }

    document.querySelectorAll("form[data-loading]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (event.defaultPrevented) return; // annulé (confirmation refusée, fichier invalide…)
            if (form.dataset.submitting) {
                event.preventDefault(); // pas de double envoi
                return;
            }
            form.dataset.submitting = "1";
            form.querySelectorAll("button[type=submit]").forEach((button) => {
                button.classList.add("is-loading");
                button.setAttribute("aria-busy", "true");
                // Désactivé après l'envoi : un bouton désactivé tout de suite ne serait pas transmis
                setTimeout(() => { button.disabled = true; }, 0);
            });
            showLoading(form);
        });
    });

    // Retour arrière du navigateur (page restaurée depuis le cache) : on réactive tout
    window.addEventListener("pageshow", (event) => {
        if (!event.persisted) return;
        document.querySelectorAll("[data-loading-status]").forEach((status) => {
            clearInterval(Number(status.dataset.timer));
            status.remove();
        });
        document.querySelectorAll("form[data-submitting]").forEach((form) => {
            delete form.dataset.submitting;
            form.querySelectorAll("button[type=submit]").forEach((button) => {
                button.disabled = false;
                button.classList.remove("is-loading");
                button.removeAttribute("aria-busy");
            });
        });
    });
})();
