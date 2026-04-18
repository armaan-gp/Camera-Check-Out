const togglePassword = document.getElementById('togglePassword');
const passwordInput = document.getElementById('userGuess');
const eyeIcon = document.getElementById('eyeIcon');

if (eyeIcon && !eyeIcon.classList.contains('fa-eye')) {
    eyeIcon.classList.add('fa-eye');
}

if (togglePassword && passwordInput && eyeIcon) {
    togglePassword.addEventListener('click', function () {
        const showingText = passwordInput.getAttribute('type') === 'password';
        passwordInput.setAttribute('type', showingText ? 'text' : 'password');

        eyeIcon.classList.toggle('fa-eye', !showingText);
        eyeIcon.classList.toggle('fa-eye-slash', showingText);
    });
}

const userInputs = {
    studentID: document.getElementById('studentIDinp')
};

for (let i = 1; i <= 5; i++) {
    userInputs[`equipmentID${i}`] = document.getElementById(`equipmentID${i}inp`);
}

const studentIDlen = 11;
const equipmentIDlen = 6;

let barcode = '';
let interval;
document.addEventListener('keydown', function(evt) {
    if (interval) {
        clearInterval(interval);
    }

    if (evt.code === 'Enter') {
        if (barcode) {
            handleBarcode(barcode);
        }
        barcode = '';
        return;
    }

    if (evt.key !== 'Shift') {
        barcode += evt.key;
    }

    interval = setInterval(() => {
        barcode = '';
    }, 20);
});

function getNoSpacesText(text) {
    return text.replace(/\s+/g, '');
}

function handleBarcode(scannedBarcode) {
    scannedBarcode = getNoSpacesText(scannedBarcode);

    if (scannedBarcode.length === studentIDlen && userInputs.studentID) {
        userInputs.studentID.value = scannedBarcode;
    } else if (scannedBarcode.length === equipmentIDlen) {
        for (let i = 1; i <= 5; i++) {
            const input = userInputs[`equipmentID${i}`];
            if (input && input.value.length === 0) {
                input.value = scannedBarcode;
                break;
            }
        }
    }
}

function removeRow(cb) {
    const row = cb.closest('tr');
    const form = cb.closest('form');
    if (form) {
        form.submit();
    }
    if (row) {
        row.remove();
    }
}

function showWarning(message) {
    let warningContainer = document.getElementById('warningAdd');
    if (!warningContainer) {
        warningContainer = document.createElement('div');
        warningContainer.id = 'warningAdd';
        document.body.prepend(warningContainer);
    }

    const warningDiv = document.createElement('div');
    warningDiv.className = 'warning';
    warningDiv.innerText = message;

    warningContainer.innerHTML = '';
    warningContainer.append(warningDiv);

    warningDiv.addEventListener('animationend', function() {
        warningDiv.remove();
    });
}

function validateInput(input) {
    if (input.id === 'studentIDinp' && !/^\d*$/.test(input.value)) {
        showWarning('Please enter numbers only for Student ID');
        input.value = '';
        return false;
    }

    if (/^equipmentID\dinp$/.test(input.id) && !/^\d*$/.test(input.value)) {
        showWarning('Please enter numbers only for Equipment IDs');
        input.value = '';
        return false;
    }

    return true;
}

Object.values(userInputs).forEach(input => {
    if (input) {
        input.addEventListener('input', function() {
            validateInput(this);
        });
    }
});

window.removeRow = removeRow;
