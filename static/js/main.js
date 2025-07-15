setTimeout(function() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
      alert.style.transition = "opacity 0.5s ease";
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 500); // remove after fade
    });
  }, 5000);




















