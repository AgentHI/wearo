function modalMarkup({ alertOnly = false }) {
  return `<dialog class="advertisement-confirm-dialog wearo-confirm-dialog" aria-labelledby="wearo-dialog-title" aria-describedby="wearo-dialog-copy"><div class="advertisement-confirm-dialog__hero"><span class="advertisement-confirm-dialog__spark advertisement-confirm-dialog__spark--one" aria-hidden="true">✦</span><span class="advertisement-confirm-dialog__spark advertisement-confirm-dialog__spark--two" aria-hidden="true">✦</span><button class="advertisement-confirm-dialog__close" data-wearo-close type="button" aria-label="Close dialog">×</button><div class="advertisement-confirm-dialog__mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path data-wearo-icon></path></svg></div></div><div class="advertisement-confirm-dialog__content"><p class="eyebrow" data-wearo-eyebrow></p><h2 id="wearo-dialog-title" data-wearo-title></h2><p id="wearo-dialog-copy" data-wearo-copy></p><div class="advertisement-confirm-dialog__notice" data-wearo-notice><span aria-hidden="true">!</span><p></p></div><div class="advertisement-confirm-dialog__actions${alertOnly ? " wearo-confirm-dialog__actions--single" : ""}">${alertOnly ? "" : '<button class="button advertisement-confirm-dialog__keep" data-wearo-cancel type="button"></button>'}<button class="button advertisement-confirm-dialog__delete" data-wearo-confirm type="button"><span></span></button></div></div></dialog>`;
}

function openWearoDialog(options = {}) {
  const alertOnly = options.alertOnly === true;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = modalMarkup({ alertOnly });
  const dialog = wrapper.firstElementChild;
  dialog.dataset.tone = options.tone || "danger";
  dialog.querySelector("[data-wearo-eyebrow]").textContent = options.eyebrow || "Wearo confirmation";
  dialog.querySelector("[data-wearo-title]").textContent = options.title || "Are you sure?";
  dialog.querySelector("[data-wearo-copy]").textContent = options.message || "Please confirm that you want to continue.";
  const notice = dialog.querySelector("[data-wearo-notice]");
  if (options.note) notice.querySelector("p").textContent = options.note;
  else notice.hidden = true;
  const confirm = dialog.querySelector("[data-wearo-confirm]");
  confirm.querySelector("span").textContent = options.confirmLabel || (alertOnly ? "Got it" : "Confirm");
  const cancel = dialog.querySelector("[data-wearo-cancel]");
  if (cancel) cancel.textContent = options.cancelLabel || "Cancel";
  dialog.querySelector("[data-wearo-icon]").setAttribute("d", options.tone === "danger" ? "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5" : "M12 3v10M12 17.5v.5");
  document.body.append(dialog);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      if (dialog.open) dialog.close();
      dialog.remove();
      resolve(value);
    };
    confirm.addEventListener("click", () => finish(true));
    cancel?.addEventListener("click", () => finish(false));
    dialog.querySelector("[data-wearo-close]").addEventListener("click", () => finish(false));
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); finish(false); });
    dialog.addEventListener("click", (event) => { if (event.target === dialog) finish(false); });
    dialog.showModal();
    confirm.focus();
  });
}

export function wearoConfirm(options) {
  return openWearoDialog(options);
}

export function wearoAlert(options) {
  return openWearoDialog({ ...options, alertOnly: true, tone: options?.tone || "info" });
}
