const historyDiv = document.getElementById('historyDiv');
const passwordDiv = document.getElementById('passwordDiv');
const passwordSubmit = document.getElementById('pSubmit');
const userGuess = document.getElementById('userGuess');
const warningDiv = document.getElementById('warningAdd');
const errorDiv = document.getElementById('errorDiv'); // Added errorDiv
let hDisplay = historyDiv ? historyDiv.style.display : 'none'; //only visible on history page
const togglePassword = document.getElementById('togglePassword');
const passwordInput = document.getElementById('userGuess');
const eyeIcon = document.getElementById('eyeIcon');

// Ensure the eye icon starts with the correct class
if (eyeIcon && !eyeIcon.classList.contains('fa-eye')) {
    eyeIcon.classList.add('fa-eye');
}

if (togglePassword && passwordInput && eyeIcon) {
    togglePassword.addEventListener('click', function () {
        const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
        passwordInput.setAttribute('type', type);

        // Toggle the eye / eye-slash icon
        if (type === 'text') {
            console.log("now become password");
            eyeIcon.classList.remove('fa-eye');
            eyeIcon.classList.add('fa-eye-slash');
        } else {
            console.log("now become text");
            eyeIcon.classList.remove('fa-eye-slash');
            eyeIcon.classList.add('fa-eye');
        }
    });
}

//the code below is the new version of this:
// const userInputs = {
//     studentID: document.getElementById('studentIDinp'),
//     equipmentID1: document.getElementById('equipmentID1inp'),
//     equipmentID2: document.getElementById('equipmentID2inp'),
//     equipmentID3: document.getElementById('equipmentID3inp'),
//     equipmentID4: document.getElementById('equipmentID4inp'),
//     equipmentID5: document.getElementById('equipmentID5inp')
// };

const userInputs = {
    studentID: document.getElementById('studentIDinp')
};

for (let i = 1; i <= 5; i++) {
    userInputs[`equipmentID${i}`] = document.getElementById(`equipmentID${i}inp`);
}

const studentIDlen = 11;
const equipmentIDlen = 6;
const historyConfig = document.getElementById('historyConfig');
const password = historyConfig ? (historyConfig.dataset.historyPassword || '') : '';

let barcode = '';
let interval;
document.addEventListener('keydown', function(evt) {
    if (interval)
        clearInterval(interval);
    if (evt.code == 'Enter') {
        if (barcode)
            handleBarcode(barcode);
        barcode = '';
        return;
    }

    if (evt.key != 'Shift')
        barcode += evt.key;
    interval = setInterval(() => barcode = '', 20);
});

function getNoSpacesText(text) {
    return text.replace(/\s+/g, '');
}

function handleBarcode(scanned_barcode) {
    scanned_barcode = getNoSpacesText(scanned_barcode);
    if (scanned_barcode.length === studentIDlen && userInputs.studentID) {
        userInputs.studentID.value = scanned_barcode;
    } else if (scanned_barcode.length === equipmentIDlen) {
        for (let i = 1; i <= 5; i++) {
            const input = userInputs[`equipmentID${i}`];
            if (input && input.value.length === 0) {
                input.value = scanned_barcode;
                break;
            }
        }
    }
}

function removeRow(cb) {
    let row = cb.closest('tr');
    let form = cb.closest('form');
    if (form) form.submit();
    if (row) row.remove();
}

if (userGuess) {
    userGuess.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && passwordSubmit) {
            passwordSubmit.click();
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    if (userGuess) userGuess.focus(); //lets user type in the input box immediately
});

if (historyDiv) historyDiv.style.display = 'none';

function showWarning(message) {
    if (warningDiv) {
        const warningDiv2 = document.createElement('div');
        warningDiv2.className = 'warning';
        warningDiv2.innerText = message;
        warningDiv.innerHTML = '';
        warningDiv.append(warningDiv2);

        // Remove after animation ends
        warningDiv2.addEventListener('animationend', function() {
            warningDiv2.remove();
        });
    }
}

// Modify your input validation to show errors immediately
function validateInput(input) {
    // Student ID: only numbers allowed
    if (input.id === 'studentIDinp' && !/^\d+$/.test(input.value)) {
        showWarning('Please enter numbers only for Student ID');
        input.value = '';
        return false;
    }
    // Equipment IDs: only numbers allowed
    if (/^equipmentID\dinp$/.test(input.id) && !/^\d+$/.test(input.value)) {
        showWarning('Please enter numbers only for Equipment IDs');
        input.value = '';
        return false;
    }
    return true;
}

// Add event listeners to your inputs
Object.values(userInputs).forEach(input => {
    if (input) {
        input.addEventListener('input', function() {
            validateInput(this);
        });
    }
});

// Update password submit warning
if (passwordSubmit) {
    passwordSubmit.addEventListener('click', function() {
        if (!userGuess) return;
        console.log("value: " + userGuess.value);
        if (userGuess.value === password) {
            if (passwordDiv) passwordDiv.remove();
            if (historyDiv) historyDiv.style.display = hDisplay;
        } else {
            showWarning('Wrong password');
        }
    });
}
