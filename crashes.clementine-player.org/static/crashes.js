// Make clicking on a table row toggle the checkbox for that row.
$(function() {
  $('tr.crash-row').click(function(eventObject) {
    if (eventObject.target.tagName != "A" &&
        eventObject.target.tagName != "INPUT") {
      var checkbox = $('td:first-child input[type=checkbox]', this);
      checkbox.prop("checked", !checkbox.prop("checked"));
    }
  });
});
