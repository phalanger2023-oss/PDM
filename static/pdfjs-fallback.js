// PDF.js : sur le serveur, la bibliothèque est servie par le site lui-même (static/vendor, ajoutée par le
// Dockerfile). En local, ce dossier n'existe pas : on charge alors PDF.js depuis Internet (cdnjs).
if (!window.pdfjsLib) {
  window.PDFJS_WORKER = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  document.write('<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"><\/script>');
}
