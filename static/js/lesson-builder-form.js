/**
 * Lesson Builder Form - Dynamic field visibility
 * Handles showing/hiding fields based on lesson type
 */

function initializeLessonForm() {
    const forms = document.querySelectorAll('form[data-lesson-form]');

    forms.forEach(form => {
        const lessonTypeSelect = form.querySelector('select[name="lesson_type"]');

        if (!lessonTypeSelect) return;

        // Initialize on page load
        updateFormFieldsVisibility(form);

        // Listen for changes
        lessonTypeSelect.addEventListener('change', function() {
            updateFormFieldsVisibility(form);
        });
    });
}

function updateFormFieldsVisibility(form) {
    const lessonType = form.querySelector('select[name="lesson_type"]').value;

    // Get all conditional fields
    const durationField = form.querySelector('.lesson-duration-field');
    const descriptionField = form.querySelector('.lesson-description-field');
    const videoUrlField = form.querySelector('.lesson-video-url-field');
    const contentFileField = form.querySelector('.lesson-content-file-field');
    const contentField = form.querySelector('.lesson-content-field');
    const quizSection = form.querySelector('.lesson-quiz-section');

    // Hide all first
    if (durationField) durationField.style.display = 'none';
    if (descriptionField) descriptionField.style.display = 'none';
    if (videoUrlField) videoUrlField.style.display = 'none';
    if (contentFileField) contentFileField.style.display = 'none';
    if (contentField) contentField.style.display = 'none';
    if (quizSection) quizSection.style.display = 'none';

    // Show based on type
    if (lessonType !== 'quiz') {
        if (durationField) durationField.style.display = 'block';
        if (descriptionField) descriptionField.style.display = 'block';
    }

    switch (lessonType) {
        case 'video':
            if (videoUrlField) videoUrlField.style.display = 'block';
            if (contentFileField) contentFileField.style.display = 'block';
            break;
        case 'pdf':
        case 'scorm':
        case 'audio':
            if (contentFileField) contentFileField.style.display = 'block';
            break;
        case 'text':
            if (contentField) contentField.style.display = 'block';
            break;
        case 'quiz':
            if (quizSection) quizSection.style.display = 'block';
            break;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeLessonForm);

// Reinitialize after HTMX swap
document.addEventListener('htmx:afterSettle', initializeLessonForm);
