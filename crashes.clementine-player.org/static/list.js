google.setOnLoadCallback(function() {
  var data = new google.visualization.DataTable();
  data.addColumn('string', 'Time');
  data.addColumn('string', 'Version');
  data.addColumn('string', 'Qt Version');
  data.addColumn('string', 'OS');
  data.addColumn('string', 'OS Version');
  data.addColumn('string', 'Status');

  data.addRows(crash_data);

  var table = new google.visualization.Table(document.getElementById('crash_table'));
  table.draw(data, {showRowNumber: true});
});
