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
  let firebaseConfig = {};
  try {
    firebaseConfig = JSON.parse(configElement.textContent || '{}');
  } catch (e) {
    console.error('Invalid Firebase Web Config JSON', e);
  }

  if (firebaseConfig.apiKey && firebaseConfig.projectId) {
    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;

      const formData = new FormData(form);
      const name = String(formData.get('name') || '').trim();
      const email = String(formData.get('email') || '').trim().toLowerCase();
      const password = String(formData.get('password') || '');

      if (form.dataset.firebaseAuth === 'signup') {
        const confirmPassword = String(formData.get('confirm_password') || '');
        if (password !== confirmPassword) {
          showMessage('Passwords do not match. Please re-enter.', true);
          return;
        }
        if (password.length < 6) {
          showMessage('Password must be at least 6 characters long.', true);
          return;
        }
      }

      submitButton.disabled = true;
      submitButton.setAttribute('aria-busy', 'true');
      const originalText = submitButton.innerHTML;
      submitButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Authenticating...';

      try {
        let credential;
        if (form.dataset.firebaseAuth === 'signup') {
          credential = await createUserWithEmailAndPassword(auth, email, password);
          if (name) {
            await updateProfile(credential.user, { displayName: name });
          }
          try {
            await sendEmailVerification(credential.user);
          } catch (verErr) {
            console.warn('Verification email non-critical error:', verErr);
          }
        } else {
          credential = await signInWithEmailAndPassword(auth, email, password);
        }

        const idToken = await getIdToken(credential.user, true);
        const response = await fetch('/auth/firebase', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ idToken, name }),
        });

        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || 'Could not complete session login.');
        }

        showMessage('Success! Redirecting...', false);
        window.location.assign(result.redirect || '/dashboard');
      } catch (error) {
        showMessage(friendlyFirebaseError(error), true);
        submitButton.disabled = false;
        submitButton.removeAttribute('aria-busy');
        submitButton.innerHTML = originalText;
      }
    });
  } else {
    console.warn('Firebase config missing or incomplete');
  }

  function showMessage(text, isError) {
    if (!message) return;
    if (!text) {
      message.hidden = true;
      message.style.display = 'none';
      return;
    }
    message.hidden = false;
    message.style.display = 'flex';
    message.className = isError ? 'flash-message flash-error' : 'flash-message flash-info';
    message.textContent = text;
  }

  function friendlyFirebaseError(error) {
    const messages = {
      'auth/email-already-in-use': 'An account with this email already exists. Sign in instead.',
      'auth/invalid-credential': 'Email or password is incorrect.',
      'auth/wrong-password': 'Incorrect password.',
      'auth/user-not-found': 'No account found with this email.',
      'auth/invalid-email': 'Please enter a valid email address.',
      'auth/weak-password': 'Password should be at least 6 characters.',
      'auth/too-many-requests': 'Too many attempts. Please wait a moment and try again.',
      'auth/network-request-failed': 'Could not reach Firebase. Check your internet connection.',
      'auth/operation-not-allowed': 'Email/Password sign-in is not enabled in Firebase Console.',
    };
    return messages[error.code] || error.message || 'Authentication failed. Please check your credentials.';
  }
}
