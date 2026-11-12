import { $, safe } from "./utils.js";
import { api, sendJSON } from "./api.js";

// Подключает формы один раз; сотрудники загружаются при открытии кабинета.
export function initAccount() {
  let staffUsers = [];
  let pendingRoleChange = null;

  function accountMessage(id, message, success = false) {
    const el = $(id);
    el.textContent = message;
    el.classList.toggle("success", success);
    el.hidden = !message;
  }
  $("profile-name-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("account-name").value.trim();
    accountMessage("name-message", "");
    try {
      const result = await sendJSON("/api/account/name", "PATCH", { name });
      $("profile-current-name").textContent = result.name;
      $("header-account").textContent = result.name;
      $("sidebar-account-name").textContent = result.name;
      document.querySelector(".profile-avatar").textContent = result.name
        .charAt(0)
        .toUpperCase();
      accountMessage("name-message", "Имя сохранено", true);
    } catch (error) {
      accountMessage("name-message", error.message);
    }
  });
  $("password-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    accountMessage("password-message", "");
    const newPassword = $("new-password").value;
    if (newPassword !== $("confirm-password").value) {
      accountMessage("password-message", "Новые пароли не совпадают");
      return;
    }
    try {
      await sendJSON("/api/account/password", "POST", {
        old_password: $("old-password").value,
        new_password: newPassword,
      });
      $("password-form").reset();
      accountMessage("password-message", "Пароль обновлён", true);
    } catch (error) {
      accountMessage("password-message", error.message);
    }
  });

  // JavaScript показывает разрешённые действия с сотрудниками;
  // сервер проверяет права и пароль повторно.

  function staffRoleAction(user, self, lastAdmin) {
    if (self) return '<span class="outline-label">Это вы</span>';
    if (user.role === "dispatcher" && user.active) {
      return `<button type="button" class="secondary-button" data-change-role="admin" data-user-id="${Number(user.id)}">Назначить администратором</button>`;
    }
    if (user.role === "admin" && !lastAdmin) {
      return `<button type="button" class="secondary-button" data-change-role="dispatcher" data-user-id="${Number(user.id)}">Сделать диспетчером</button>`;
    }
    return "";
  }

  function renderUsers() {
    const myId = Number($("staff-list").dataset.currentUserId);
    const activeAdmins = staffUsers.filter(
      (user) => user.role === "admin" && user.active,
    ).length;
    $("staff-list").innerHTML =
      staffUsers
        .map((user) => {
          const self = Number(user.id) === myId;
          const lastAdmin =
            user.role === "admin" && user.active && activeAdmins <= 1;
          const roleAction = staffRoleAction(user, self, lastAdmin);
          const toggle =
            self || lastAdmin
              ? ""
              : `<button type="button" class="secondary-button" data-staff-id="${Number(user.id)}" data-staff-active="${!user.active}">${user.active ? "Отключить" : "Разрешить вход"}</button>`;
          const note = lastAdmin
            ? '<span class="staff-note">Последний активный администратор</span>'
            : "";
          return `<div class="staff-item">
        <div><strong>${safe(user.name)}</strong>
          <small>${safe(user.email)} · ${user.role === "admin" ? "Администратор" : "Диспетчер"}${user.active ? "" : " · Нет доступа (заявка или отключён)"}</small>
          ${note}</div>
        <div class="staff-actions">${roleAction}${toggle}</div>
      </div>`;
        })
        .join("") || '<p class="empty">Сотрудников пока нет</p>';
  }

  async function loadUsers() {
    if (!$("staff-list")) return;
    try {
      staffUsers = await api("/api/users");
      renderUsers();
      accountMessage("staff-error", "");
    } catch (error) {
      accountMessage("staff-error", error.message);
    }
  }

  if ($("staff-form")) {
    $("staff-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await sendJSON("/api/users", "POST", {
          name: $("staff-name").value.trim(),
          email: $("staff-email").value.trim(),
          password: $("staff-password").value,
        });
        $("staff-form").reset();
        await loadUsers();
        accountMessage("staff-error", "Сотрудник создан", true);
      } catch (error) {
        accountMessage("staff-error", error.message);
      }
    });

    // Повышение/понижение подтверждается в настоящем диалоговом окне, а не prompt().
    const roleDialog = $("staff-role-dialog");
    const closeRoleDialog = () => {
      roleDialog.close();
      $("staff-role-form").reset();
      $("staff-role-error").hidden = true;
      pendingRoleChange = null;
    };
    $("close-staff-role").addEventListener("click", closeRoleDialog);
    $("cancel-staff-role").addEventListener("click", closeRoleDialog);
    roleDialog.addEventListener("close", () => {
      $("staff-role-form").reset();
      pendingRoleChange = null;
    });
    $("staff-list").addEventListener("click", async (event) => {
      const roleButton = event.target.closest("[data-change-role]");
      if (roleButton) {
        const user = staffUsers.find(
          (u) => u.id === Number(roleButton.dataset.userId),
        );
        if (!user) return;
        pendingRoleChange = { id: user.id, role: roleButton.dataset.changeRole };
        $("staff-role-description").textContent =
          `Сотрудник: ${user.name}. Новая роль: ${pendingRoleChange.role === "admin" ? "администратор" : "диспетчер"}.`;
        $("staff-role-form").reset();
        $("staff-role-error").hidden = true;
        roleDialog.showModal();
        $("staff-role-password").focus();
        return;
      }
      const button = event.target.closest("[data-staff-id]");
      if (!button) return;
      const newActive = button.dataset.staffActive === "true";
      // Выключение чужого доступа — важное действие, подтверждаем его явно.
      if (!newActive && !window.confirm("Отключить доступ этого сотрудника?"))
        return;
      button.disabled = true;
      try {
        await sendJSON(`/api/users/${button.dataset.staffId}/active`, "PATCH", {
          active: newActive,
        });
        await loadUsers();
        accountMessage(
          "staff-error",
          newActive ? "Вход разрешён" : "Доступ отключён",
          true,
        );
      } catch (error) {
        button.disabled = false;
        accountMessage("staff-error", error.message);
      }
    });
    $("staff-role-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!pendingRoleChange) return;
      const button = $("confirm-staff-role");
      button.disabled = true;
      $("staff-role-error").hidden = true;
      try {
        await sendJSON(`/api/users/${pendingRoleChange.id}/role`, "PATCH", {
          role: pendingRoleChange.role,
          password: $("staff-role-password").value,
        });
        closeRoleDialog();
        await loadUsers();
        accountMessage("staff-error", "Роль сотрудника сохранена", true);
      } catch (error) {
        $("staff-role-error").textContent = error.message;
        $("staff-role-error").hidden = false;
        $("staff-role-password").value = "";
      } finally {
        button.disabled = false;
      }
    });
  }

  return { loadUsers };
}
