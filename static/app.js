(() => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  if (token) {
    document.querySelectorAll('form[method="post" i]').forEach((form) => {
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
        if (form.dataset.submitting === '1') return;
        form.dataset.submitting = '1';
        try {
          const response = await fetch(form.action || location.href, {
            method: 'POST',
            body: new FormData(form),
            redirect: 'follow',
            headers: {'X-CSRF-Token': token},
            credentials: 'same-origin'
          });
          if (response.redirected) {
            location.assign(response.url);
            return;
          }
          if (!response.ok) {
            document.documentElement.innerHTML = await response.text();
            return;
          }
          location.reload();
        } catch (error) {
          window.alert('Die Aktion konnte nicht ausgeführt werden.');
          form.dataset.submitting = '0';
        }
      });
    });
  }

  const search = document.getElementById('project-search');
  if (search) {
    const cards = [...document.querySelectorAll('.project-tile')];
    const empty = document.getElementById('search-empty');
    search.addEventListener('input', () => {
      const term = search.value.trim().toLocaleLowerCase('de');
      let shown = 0;
      cards.forEach((card) => {
        const visible = card.dataset.search.includes(term);
        card.hidden = !visible;
        if (visible) shown += 1;
      });
      empty.hidden = shown !== 0;
    });
  }
})();
