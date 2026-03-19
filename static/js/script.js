document.addEventListener('DOMContentLoaded', () => {
    // File upload preview logic
    const fileInputs = document.querySelectorAll('input[type="file"]');

    fileInputs.forEach(input => {
        input.addEventListener('change', function () {
            const previewElement = this.parentElement.querySelector('.file-preview');
            if (previewElement && this.files && this.files.length > 0) {
                const fileName = this.files[0].name;
                previewElement.innerHTML = `<span style="color: #3b82f6; font-weight: 600;">📁 ${fileName}</span>`;
            } else if (previewElement) {
                previewElement.innerHTML = 'Drag and drop or click to upload';
            }
        });
    });
});
