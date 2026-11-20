/* Passage d'un quiz : une question à la fois, progression, confirmation avant l'envoi.
   Sans JavaScript, toutes les questions restent affichées et le formulaire fonctionne. */
(function () {
    "use strict";

    const form = document.querySelector("[data-quiz-form]");
    if (!form) return;

    const questions = Array.from(form.querySelectorAll("[data-question]"));
    const total = questions.length;
    const progress = form.querySelector("[data-quiz-progress]");
    const position = form.querySelector("[data-quiz-position]");
    const answeredLabel = form.querySelector("[data-quiz-answered]");
    const bar = form.querySelector("[data-quiz-bar]");
    const dotsBox = form.querySelector("[data-quiz-dots]");
    const previous = form.querySelector("[data-quiz-prev]");
    const next = form.querySelector("[data-quiz-next]");
    let current = 0;

    function isAnswered(question) {
        return question.querySelector("input[type=radio]:checked") !== null;
    }

    function answeredCount() {
        return questions.filter(isAnswered).length;
    }

    // Un bouton par question pour y accéder directement
    const dots = questions.map((question, index) => {
        const dot = document.createElement("button");
        dot.type = "button";
        dot.className = "quiz-dot";
        dot.textContent = String(index + 1);
        dot.setAttribute("aria-label", "Question " + (index + 1));
        dot.addEventListener("click", () => show(index, true));
        dotsBox.appendChild(dot);
        return dot;
    });

    function updateProgress() {
        const answered = answeredCount();
        bar.value = answered;
        answeredLabel.textContent = answered + " réponse(s) sur " + total;
        questions.forEach((question, index) => {
            const done = isAnswered(question);
            dots[index].classList.toggle("is-answered", done);
            dots[index].setAttribute(
                "aria-label", "Question " + (index + 1) + (done ? ", répondue" : ", sans réponse")
            );
        });
    }

    function show(index, moveFocus) {
        current = Math.max(0, Math.min(index, total - 1));
        questions.forEach((question, i) => { question.hidden = i !== current; });
        dots.forEach((dot, i) => {
            if (i === current) dot.setAttribute("aria-current", "step");
            else dot.removeAttribute("aria-current");
        });
        position.textContent = "Question " + (current + 1) + " sur " + total;
        previous.hidden = current === 0;
        next.hidden = current === total - 1;
        if (moveFocus) questions[current].focus();
    }

    if (total > 1) {
        progress.hidden = false;
        previous.addEventListener("click", () => show(current - 1, true));
        next.addEventListener("click", () => show(current + 1, true));
        show(0, false);
    }
    form.addEventListener("change", updateProgress);
    updateProgress();

    form.addEventListener("submit", (event) => {
        if (form.dataset.submitting) {
            event.preventDefault();
            return;
        }
        const missing = total - answeredCount();
        const message = missing
            ? "Il reste " + missing + " question(s) sans réponse : elles compteront comme fausses. Envoyer quand même ?"
            : "Envoyer vos réponses ? Vous ne pourrez plus les modifier.";
        if (!window.confirm(message)) {
            event.preventDefault();
            if (missing) {
                const firstMissing = questions.findIndex((question) => !isAnswered(question));
                if (total > 1) show(firstMissing, true);
            }
            return;
        }
        form.dataset.submitting = "1";
    });
})();
