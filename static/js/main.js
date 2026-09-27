document.querySelectorAll('.password-toggle').forEach((toggle) => {
  toggle.addEventListener('click', () => {
    const field = toggle.parentElement.querySelector('input');
    const showing = field.type === 'password';
    field.type = showing ? 'text' : 'password';
    toggle.setAttribute('aria-label', showing ? 'Hide password' : 'Show password');
    toggle.innerHTML = `<i class="fa-regular ${showing ? 'fa-eye-slash' : 'fa-eye'}"></i>`;
  });
});

document.querySelectorAll('form').forEach((form) => {
  form.addEventListener('submit', () => {
    if (form.hasAttribute('data-firebase-auth')) return;
    const button = form.querySelector('button[type="submit"]');
    if (!button || !form.checkValidity()) return;
    button.disabled = true;
    button.classList.add('is-loading');
    button.setAttribute('aria-busy', 'true');
  });
});
