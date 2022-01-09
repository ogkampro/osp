function clearListNotification(notificationID) {
    var listEntry = document.getElementById('notificationList-' + notificationID);
    listEntry.parentNode.removeChild(listEntry);
    clearNotification(notificationID);
    if (notificationCount <= 0) {
        emptyNotificationList.style.display = "block";
    }
}

function clearAllListNotifications() {
  var ids = $('.notificationBodyFull .notification-box').map(function(){
    return $(this).attr('id');
    }).get();
  ids.forEach(function (item, index) {
    if (item != 'notificationList-empty') {
      item = item.replace('notificationList-','');
      clearNotification(item);
    }
  });
  if (notificationCount <= 0) {
    emptyNotificationList.style.display = "block";
  }
}

function clearNotification(notificationID) {
  socket.emit('markNotificationAsRead', { data: notificationID });
  notificationCount = notificationCount - 1;
}