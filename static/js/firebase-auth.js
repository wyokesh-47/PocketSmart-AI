import { initializeApp } from 'https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js';
import {
  createUserWithEmailAndPassword,
  getAuth,
  getIdToken,
  sendEmailVerification,
  signInWithEmailAndPassword,
  updateProfile,
} from 'https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js';

const form = document.querySelector('[data-firebase-auth]');
const message = form?.querySelector('[data-auth-message]');
const submitButton = form?.querySelector('button[type="submit"]');
const configElement = document.getElementById('firebaseWebConfig');

if (form && configElement) {
  const firebaseConfig = JSON.parse(configElement.textContent);
  const auth = getAuth(initializeApp(firebaseConfig));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;

    const formData = new FormData(form);
    const name = String(formData.get('name') || '').trim();
    const email = String(formData.get('email') || '').trim().toLowerCase();
    const password = String(formData.get('password') || '');
    if (form.dataset.firebaseAuth === 'signup' && password !== formData.get('confirm_password')) {
      showMessage('Passwords do not match. Please re-enter.', true);
      return;
    }

    submitButton.disabled = true;
    submitButton.setAttribute('aria-busy', 'true');
    try {
      let credential;
      if (form.dataset.firebaseAuth === 'signup') {
        credential = await createUserWithEmailAndPassword(auth, email, password);
        await updateProfile(credential.user, {displayName: name});
        await sendEmailVerification(credential.user);
        showMessage('Check your email and verify your address, then sign in.', false);
        submitButton.disabled = false;
        submitButton.removeAttribute('aria-busy');
        return;
      } else {
        credential = await signInWithEmailAndPassword(auth, email, password);
      }
      const idToken = await getIdToken(credential.user, true);
      const response = await fetch('/auth/firebase', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({idToken, name}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not finish sign-in.');
      window.location.assign(result.redirect || '/dashboard');
    } catch (error) {
      showMessage(friendlyFirebaseError(error), true);
      submitButton.disabled = false;
      submitButton.removeAttribute('aria-busy');
    }
  });

  function showMessage(text, isError) {
    if (!message) return;
    message.hidden = false;
    message.classList.toggle('flash-error', isError);
    message.classList.toggle('flash-info', !isError);
    message.textContent = text;
  }

  function friendlyFirebaseError(error) {
    const messages = {
      'auth/email-already-in-use': 'An account with this email already exists. Sign in instead.',
      'auth/invalid-credential': 'Email or password is incorrect.',
      'auth/invalid-email': 'Enter a valid email address.',
      'auth/weak-password': 'Use a stronger password with at least 6 characters.',
      'auth/too-many-requests': 'Too many attempts. Wait a little and try again.',
      'auth/network-request-failed': 'Could not reach Firebase. Check your connection.',
    };
    return messages[error.code] || error.message || 'Firebase sign-in failed. Check the Firebase project configuration.';
  }
}
