(function () {
    const form = document.getElementById("chat-form");
    if (!form) return;

    const box = document.getElementById("chat-messages");
    const textarea = form.querySelector("textarea");
    const button = form.querySelector("button[type=submit]");
    box.scrollTop = box.scrollHeight;

    function pageLabel(source) {
        return source.page_start === source.page_end
            ? "page " + source.page_start
            : "pages " + source.page_start + " à " + source.page_end;
    }

    function addMessage(role, text) {
        const empty = document.getElementById("chat-empty");
        if (empty) empty.remove();

        const wrapper = document.createElement("div");
        wrapper.className = "chat-message chat-" + role;
        const bubble = document.createElement("div");
        bubble.className = "chat-bubble";
        bubble.textContent = text; // jamais de HTML venant du modèle
        wrapper.appendChild(bubble);
        box.appendChild(wrapper);
        box.scrollTop = box.scrollHeight;
        return wrapper;
    }

    function addSources(wrapper, sources) {
        if (!sources.length) return;
        const list = document.createElement("ul");
        list.className = "chat-sources";
        sources.forEach((source) => {
            const item = document.createElement("li");
            if (source.cited) item.className = "cited";
            let label = "[" + source.n + "] " + pageLabel(source);
            if (source.chapter) label += " · " + source.chapter;
            const strong = document.createElement("strong");
            strong.textContent = label;
            const excerpt = document.createElement("span");
            excerpt.className = "meta";
            excerpt.textContent = " — " + source.excerpt + "…";
            item.append(strong, excerpt);
            list.appendChild(item);
        });
        wrapper.appendChild(list);
        box.scrollTop = box.scrollHeight;
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const question = textarea.value.trim();
        if (!question) return;

        const data = new FormData(form); // à créer avant de désactiver les champs
        addMessage("user", question);
        textarea.value = "";
        textarea.disabled = true;
        button.disabled = true;
        const pending = addMessage("assistant", "Réflexion en cours…");
        pending.classList.add("chat-pending");

        try {
            const response = await fetch(form.action, { method: "POST", body: data });
            let payload = {};
            try {
                payload = await response.json();
            } catch (error) {
                /* réponse non JSON */
            }
            pending.remove();
            if (!response.ok) {
                addMessage("error", payload.error || "Erreur " + response.status);
            } else {
                const wrapper = addMessage("assistant", payload.answer);
                addSources(wrapper, payload.sources || []);
            }
        } catch (error) {
            pending.remove();
            addMessage("error", "Impossible de joindre le serveur.");
        } finally {
            textarea.disabled = false;
            button.disabled = false;
            textarea.focus();
        }
    });

    // Entrée envoie, Maj+Entrée va à la ligne
    textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
})();