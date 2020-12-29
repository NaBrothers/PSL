create table IF NOT EXISTS `users` (
  `ID` smallint(6) NOT NULL auto_increment,
  `QQ` int(11) NOT NULL UNIQUE,
  `Name` varchar(50) default null,
  `Level` int(11) default null,
  primary key(`id`)
) default charset = utf8;