create table IF NOT EXISTS `global` (
  `ID` int(11) NOT NULL auto_increment,
  `Name` VARCHAR(20) NOT NULL,
  `Value` VARCHAR(20) NOT NULL,
  primary key(`ID`)
) default charset = utf8;