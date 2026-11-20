/* Chatbot : envoi par Fetch API, « Réflexion en cours » animé avec minuteur,
   sources repliables, bouton « Copier », zone de saisie qui s'agrandit,
   conservation de la question en cas d'erreur. */
(function () {
    "use strict";

    const form = document.getElementById("chat-form");
    if (!form) return;

    const box = document.getElementById("chat-messages");
    const textarea = form.querySelector("textarea");
    const button = form.querySelector("button[type=submit]");
    const timeoutSeconds = Number(form.dataset.timeout) || 120;
    const SLOW_AFTER_SECONDS = 60;
    const SVG_NS = "http://www.w3.org/2000/svg";

    function scrollToBottom() {
        box.scrollTop = box.scrollHeight;
    }
    scrollToBottom();

    function icon(name) {
        const svg = document.createElementNS(SVG_NS, "svg");
        svg.setAttribute("class", "icon");
        svg.setAttribute("aria-hidden", "true");
        svg.setAttribute("focusable", "false");
        const use = document.createElementNS(SVG_NS, "use");
        use.setAttribute("href", "#icon-" + name);
        svg.appendChild(use);
        return svg;
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text; // jamais innerHTML : le texte du modèle n'est pas du HTML
        return node;
    }

    function pageLabel(source) {
        return source.page_start === source.page_end
            ? "page " + source.page_start
            : "pages " + source.page_start + " à " + source.page_end;
    }

    function now() {
        return new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    }

    function addMessage(role, text) {
        const empty = document.getElementById("chat-empty");
        if (empty) empty.remove();
        const message = element("div", "message message--" + role);
        message.appendChild(element("div", "message__bubble", text));
        if (role !== "error") {
            const who = role === "user" ? "Vous" : "Assistant";
            message.appendChild(element("span", "message__meta", who + " · " + now()));
        }
        box.appendChild(message);
        scrollToBottom();
        return message;
    }

    function addTools(message, sources) {
        const tools = element("div", "message__tools");
        const copy = element("button", "btn btn-ghost btn-sm");
        copy.type = "button";
        copy.dataset.copy = "";
        copy.append(icon("copy"));
        const label = element("span", "", "Copier");
        label.dataset.copyLabel = "";
        copy.append(label);
        tools.appendChild(copy);

        if (sources.length) {
            const details = element("details", "sources");
            details.appendChild(element("summary", "", "Sources (" + sources.length + ")"));
            const list = element("ol", "source-list");
            sources.forEach((source) => {
                const item = element("li", "source" + (source.cited ? " is-cited" : ""));
                const number = element("span", "source__number", String(source.n));
                number.setAttribute("aria-hidden", "true");
                item.append(number);
                item.append(element("span", "source__pages",
                    pageLabel(source) + (source.cited ? " · citée dans la réponse" : "")));
                if (source.chapter) item.append(element("span", "source__chapter", source.chapter));
                item.append(element("span", "source__excerpt", "« " + source.excerpt + "… »"));
                list.appendChild(item);
            });
            details.appendChild(list);
            tools.appendChild(details);
        }
        message.appendChild(tools);
        scrollToBottom();
    }

    /* ---------- Bouton « Copier » ---------- */
    async function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
            return;
        }
        // Repli quand l'API presse-papiers est indisponible (http:// hors localhost)
        const helper = element("textarea", "sr-only");
        helper.value = text;
        helper.setAttribute("readonly", "");
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        helper.remove();
    }

    box.addEventListener("click", async (event) => {
        const copyButton = event.target.closest("[data-copy]");
        if (!copyButton) return;
        const label = copyButton.querySelector("[data-copy-label]") || copyButton;
        const bubble = copyButton.closest(".message").querySelector(".message__bubble");
        try {
            await copyText(bubble.textContent);
            label.textContent = "Copié ✓";
        } catch (error) {
            label.textContent = "Copie impossible";
        }
        setTimeout(() => { label.textContent = "Copier"; }, 2000);
    });

    /* ---------- « Réflexion en cours » : points animés + temps écoulé ---------- */
    function addPending() {
        const empty = document.getElementById("chat-empty");
        if (empty) empty.remove();
        const message = element("div", "message message--assistant message--pending");
        const bubble = element("div", "message__bubble");
        const line = element("span", "", "Réflexion en cours");
        const dots = element("span", "typing");
        dots.setAttribute("aria-hidden", "true");
        dots.append(element("span"), element("span"), element("span"));
        const hint = element("span", "pending__hint");
        bubble.append(line, dots, hint);
        message.appendChild(bubble);
        box.appendChild(message);
        scrollToBottom();

        const started = Date.now();
        const render = () => {
            const seconds = Math.round((Date.now() - started) / 1000);
            let text = seconds + " s écoulées · un modèle local répond souvent en une à deux minutes.";
            if (seconds >= SLOW_AFTER_SECONDS) {
                text = seconds + " s écoulées · toujours en cours. La réponse arrivera, ou un message " +
                    "d'erreur s'affichera au bout de " + timeoutSeconds + " s.";
            }
            hint.textContent = text;
        };
        render();
        const timer = setInterval(render, 1000);
        return () => { clearInterval(timer); message.remove(); };
    }

    /* ---------- Zone de saisie qui s'agrandit avec le texte ---------- */
    function autosize() {
        textarea.style.height = "auto";
        textarea.style.height = Math.min(textarea.scrollHeight + 2, 200) + "px";
    }
    textarea.addEventListener("input", autosize);

    function setBusy(busy) {
        textarea.disabled = busy;
        button.disabled = busy;
        button.classList.toggle("is-loading", busy);
        button.setAttribute("aria-busy", String(busy));
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const question = textarea.value.trim();
        if (!question || button.disabled) return;

        const data = new FormData(form); // à créer avant de désactiver les champs
        const userMessage = addMessage("user", question);
        textarea.value = "";
        autosize();
        setBusy(true);
        const stopPending = addPending();

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), timeoutSeconds * 1000);
        let errorText = "";

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: data,
                signal: controller.signal,
                headers: { "X-Requested-With": "fetch" },
            });
            let payload = {};
            try {
                payload = await response.json();
            } catch (error) {
                /* réponse non JSON (page d'erreur, coupure…) */
            }
            stopPending();
            if (response.ok) {
                const message = addMessage("assistant", payload.answer);
                addTools(message, payload.sources || []);
            } else {
                errorText = payload.error || "Erreur du serveur (" + response.status + ").";
            }
        } catch (error) {
            stopPending();
            errorText = error.name === "AbortError"
                ? "Délai dépassé : le navigateur a cessé d'attendre après " + timeoutSeconds + " s. " +
                  "Si le serveur termine malgré tout, la réponse apparaîtra en rechargeant la page."
                : "Impossible de joindre le serveur. Vérifiez votre connexion.";
        } finally {
            clearTimeout(timeout);
            setBusy(false);
        }

        if (errorText) {
            // Le serveur n'a rien enregistré : on retire la question affichée et on la rend
            // à l'étudiant pour qu'il puisse la renvoyer sans la retaper.
            userMessage.remove();
            addMessage("error", errorText + " Votre question a été conservée dans la zone de saisie.");
            textarea.value = question;
            autosize();
        }
        textarea.focus();
    });

    // Entrée envoie, Maj+Entrée va à la ligne
    textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
})();
