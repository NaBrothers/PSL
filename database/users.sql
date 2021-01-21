create table IF NOT EXISTS `users` (
  `ID` smallint(6) NOT NULL auto_increment,
  `QQ` bigint NOT NULL UNIQUE,
  `Name` varchar(50) default null,
  `Level` int(11) default null,
  `Money` int(11) default null,
  `Formation` varchar(16) default "442",
  `isAdmin` boolean default false,
  primary key(`ID`)
) default charset = utf8;