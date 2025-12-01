const usernameForm = document.getElementById("username-form");
const detailsCard = document.getElementById("details-card");
const detailsForm = document.getElementById("details-form");
const detailsUsername = document.getElementById("details-username");
const detailsTitle = document.getElementById("details-title");
const detailsDescription = document.getElementById("details-description");
const detailsSubmitBtn = document.getElementById("details-submit-btn");
const resultCard = document.getElementById("result-card");
const userJson = document.getElementById("user-json");
const summaryEl = document.getElementById("summary");
const toast = document.getElementById("toast");
const cancelDetails = document.getElementById("cancel-details");
const editProfileBtn = document.getElementById("edit-profile-btn");
const generateWorkoutBtn = document.getElementById("generate-workout-btn");
const workoutCard = document.getElementById("workout-card");
const workoutPlanEl = document.getElementById("workout-plan");
const closeWorkoutBtn = document.getElementById("close-workout-btn");
const workoutRefineForm = document.getElementById("workout-refine-form");
const workoutAdditionalRequirements = document.getElementById("workout-additional-requirements");
const refineWorkoutBtn = document.getElementById("refine-workout-btn");

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("hidden", false);
  toast.style.borderColor = isError ? "#f87171" : "#4ade80";
  setTimeout(() => toast.classList.add("hidden"), 3500);
}

let isEditMode = false;

function toggleDetails(show, editUser = null) {
  detailsCard.classList.toggle("hidden", !show);
  if (show && editUser) {
    // Edit mode: populate form with user data
    isEditMode = true;
    detailsTitle.textContent = "Edit Profile";
    detailsDescription.textContent = "Update your profile information below.";
    detailsSubmitBtn.textContent = "Update Profile";
    detailsUsername.value = editUser.username;
    detailsForm.age.value = editUser.age || "";
    detailsForm.height.value = editUser.height || "";
    detailsForm.weight.value = editUser.weight || "";
    detailsForm.exercise_minutes.value = editUser.exercise_minutes || "";
    detailsForm.intensity.value = editUser.intensity || "";
    detailsForm.mood.value = editUser.mood || "";
    detailsForm.restrictions.value = editUser.restrictions || "";
    detailsForm.goals.value = editUser.goals || "";
    detailsForm.daily_goal.value = editUser.daily_goal || "";
  } else {
    // Create mode: reset form
    isEditMode = false;
    detailsTitle.textContent = "Tell us more";
    detailsDescription.textContent = "We could not find that username. Share a few quick details to create a plan.";
    detailsSubmitBtn.textContent = "Save profile";
    if (!show) {
      detailsForm.reset();
    }
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

async function putJson(url, payload) {
  const response = await fetch(url, {
    method: "PUT",
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
    let data;
    if (isEditMode) {
      // Update existing user
      data = await putJson(`/api/users/${formData.username}`, formData);
      showToast("Profile updated");
    } else {
      // Create new user
      data = await postJson("/api/users", formData);
      showToast("Profile created");
    }
    renderUser(data.user, data.summary);
    toggleDetails(false);
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
  workoutRefineForm.style.display = "none"; // Hide refine form initially

  try {
    const data = await postJson("/api/workout-plan", { 
      username: currentUser.username,
      is_follow_up: false
    });
    if (data.status === "success") {
      workoutPlanEl.innerHTML = `<pre style="white-space: pre-wrap; font-family: inherit;">${data.workout_plan}</pre>`;
      workoutRefineForm.style.display = "flex"; // Show refine form after initial plan
      workoutAdditionalRequirements.value = ""; // Clear previous requirements
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
  workoutAdditionalRequirements.value = ""; // Clear form when closing
});

workoutRefineForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentUser) {
    showToast("No user profile available", true);
    return;
  }

  const additionalRequirements = workoutAdditionalRequirements.value.trim();
  if (!additionalRequirements) {
    showToast("Please enter additional requirements", true);
    return;
  }

  const previousPlan = workoutPlanEl.innerHTML;
  workoutPlanEl.textContent = "Refining workout plan with your additional requirements...";
  refineWorkoutBtn.disabled = true;

  try {
    const data = await postJson("/api/workout-plan", {
      username: currentUser.username,
      additional_requirements: additionalRequirements,
      is_follow_up: true
    });
    
    if (data.status === "success") {
      workoutPlanEl.innerHTML = `<pre style="white-space: pre-wrap; font-family: inherit;">${data.workout_plan}</pre>`;
      workoutAdditionalRequirements.value = ""; // Clear form after successful refinement
      showToast("Workout plan refined with your additional requirements");
    } else {
      workoutPlanEl.innerHTML = previousPlan; // Restore previous plan on error
      throw new Error(data.error || "Failed to refine workout plan");
    }
  } catch (err) {
    workoutPlanEl.innerHTML = previousPlan; // Restore previous plan on error
    showToast(err.message, true);
  } finally {
    refineWorkoutBtn.disabled = false;
  }
});

editProfileBtn.addEventListener("click", () => {
  if (!currentUser) {
    showToast("No user profile available", true);
    return;
  }
  toggleDetails(true, currentUser);
  resultCard.classList.add("hidden");
});

