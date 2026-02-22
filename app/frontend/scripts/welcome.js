/**
 * welcome.js - Startup routing for welcome screen.
 */

let hasNavigated = false;

function goTo(page) {
  if (hasNavigated) return;
  hasNavigated = true;
  window.location.href = page;
}

async function bootstrapRoute() {
  try {
    const boot = await window.eyeApi.bootstrap();

    if (boot.recommended_page && boot.recommended_page !== 'welcome.html') {
      goTo(boot.recommended_page);
      return;
    }

    setTimeout(() => goTo('connect.html'), 2000);
  } catch (err) {
    setTimeout(() => goTo('connect.html'), 2000);
  }
}

document.body.addEventListener('click', () => goTo('connect.html'));
bootstrapRoute();
