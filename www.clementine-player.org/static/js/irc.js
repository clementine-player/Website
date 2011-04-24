/**
 * Clementine Drupal Theme
 *
 * @license Code: GNU/AGPL http://www.fsf.org/licensing/licenses/agpl-3.0.html
 * @license Graphics : CC-BY-SA http://creativecommons.org/licenses/by-sa/3.0/
 * @author Havok - Carlos Jenkins PÃ©rez <cjenkins@softwarelibrecr.org>
 * @copyright Carlos Jenkins, 2010
 * @link http://www.cjenkins.net/
 *
 * Tested with JQuery 1.12.2.3 and Drupal 6.X
 */

function expandirc() {
  irc = document.getElementById("irc");
  ul = document.getElementById("irclink");
  irc.className = "irccontainer";
  ul.className = "hidden";
}
