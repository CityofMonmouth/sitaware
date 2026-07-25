document.addEventListener('submit', function (e) {
  var form = e.target;
  if (form.hasAttribute('data-confirm')) {
    if (!window.confirm(form.getAttribute('data-confirm'))) {
      e.preventDefault();
    }
  }
});

// Auto-submit the filter form when a dropdown changes. This lives here
// rather than as an inline onchange="" attribute because the Content-
// Security-Policy blocks inline event handlers — an inline version silently
// does nothing at all in the browser.
document.addEventListener('change', function (e) {
  var el = e.target;
  if (el.hasAttribute && el.hasAttribute('data-autosubmit') && el.form) {
    el.form.submit();
  }
});
