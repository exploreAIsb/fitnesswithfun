const usernameForm = document.getElementById("username-form");
const detailsCard = document.getElementById("details-card");
const detailsForm = document.getElementById("details-form");
const detailsUsername = document.getElementById("details-username");
const resultCard = document.getElementById("result-card");
const userJson = document.getElementById("user-json");
const summaryEl = document.getElementById("summary");
const toast = document.getElementById("toast");
const cancelDetails = document.getElementById("cancel-details");
const generateWorkoutBtn = document.getElementById("generate-workout-btn");
const workoutCard = document.getElementById("workout-card");
const workoutPlanEl = document.getElementById("workout-plan");
const closeWorkoutBtn = document.getElementById("close-workout-btn");

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("hidden", false);
  toast.style.borderColor = isError ? "#f87171" : "#4ade80";
  setTimeout(() => toast.classList.add("hidden"), 3500);
}

function toggleDetails(show) {
  detailsCard.classList.toggle("hidden", !show);
  if (!show) {
    detailsForm.reset();
  }
}


async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || "Request failed");
  }
  return response.json();
}

usernameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = event.target.username.value.trim();
  if (!username) return;

  toggleDetails(false);
  resultCard.classList.add("hidden");

  try {
    const data = await postJson("/api/users/lookup", { username });
    if (data.status === "found") {
      renderUser(data.user, data.summary);
      showToast("User retrieved from SQLite");
    } else {
      detailsUsername.value = username;
      toggleDetails(true);
    }
  } catch (err) {
    showToast(err.message, true);
  }
});

detailsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = Object.fromEntries(new FormData(detailsForm));
  formData.username = detailsUsername.value;

  try {
    const data = await postJson("/api/users", formData);
    renderUser(data.user, data.summary);
    toggleDetails(false);
    showToast("Profile created");
  } catch (err) {
    showToast(err.message, true);
  }
});

cancelDetails.addEventListener("click", () => toggleDetails(false));

let currentUser = null;

function renderUser(user, summary) {
  currentUser = user;
  resultCard.classList.remove("hidden");
  userJson.textContent = JSON.stringify(user, null, 2);
  summaryEl.textContent = summary || "Gemini summary pending...";
}

generateWorkoutBtn.addEventListener("click", async () => {
  if (!currentUser) {
    showToast("No user profile available", true);
    return;
  }

  workoutPlanEl.textContent = "Generating workout plan from Kaggle dataset...";
  workoutCard.classList.remove("hidden");
  generateWorkoutBtn.disabled = true;

  try {
    const data = await postJson("/api/workout-plan", { username: currentUser.username });
    if (data.status === "success") {
      workoutPlanEl.innerHTML = `<pre style="white-space: pre-wrap; font-family: inherit;">${data.workout_plan}</pre>`;
      showToast("Workout plan generated from Kaggle dataset");
    } else {
      throw new Error(data.error || "Failed to generate workout plan");
    }
  } catch (err) {
    workoutPlanEl.textContent = `Error: ${err.message}`;
    showToast(err.message, true);
  } finally {
    generateWorkoutBtn.disabled = false;
  }
});

closeWorkoutBtn.addEventListener("click", () => {
  workoutCard.classList.add("hidden");
});

